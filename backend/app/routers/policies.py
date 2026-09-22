from fastapi import APIRouter, Depends, HTTPException
from mistralai.client import Mistral
from ..config import MISTRAL_API_KEY, MISTRAL_TIMEOUT_MS
from ..database import shared_policy_connection
from ..manufacture_data.policy_generation_service import _json_object, _response_text
from ..schemas import PolicyCopilotRequest
from ..security import current_user
from ..telemetry import observe_ai

router = APIRouter()

@router.get("/api/policies")
def policies(_: dict = Depends(current_user)):
    with shared_policy_connection() as connection:
        rows = connection.execute("""
            SELECT policy_id, library_policy_id, policy_code, title, version, policy_category,
                   parent_policy, clause_number, display_order, effective_date, status,
                   summary, page_count, file_name, document_format, source_type,
                   policy_type, mistral_document_id,
                   mistral_library_id, created_at
            FROM policy_documents ORDER BY display_order, policy_id LIMIT 1000
        """).fetchall()
    return rows


@router.get("/api/policies/{policy_id}/relationships")
def policy_relationships(policy_id: int, _: dict = Depends(current_user)):
    with shared_policy_connection() as connection:
        policy = connection.execute(
            "SELECT policy_id FROM policy_documents WHERE policy_id = %s",
            (policy_id,),
        ).fetchone()
        if not policy:
            raise HTTPException(status_code=404, detail="Policy document not found")
        return connection.execute("""
            SELECT relationship.relationship_id,
                   related.policy_id AS related_policy_id,
                   related.library_policy_id AS related_library_policy_id,
                   related.policy_code AS related_policy_code,
                   related.title AS related_policy_name,
                   related.policy_type AS related_policy_type,
                   relationship.relationship_type,
                   relationship.relationship_strength,
                   relationship.rationale
            FROM policy_relationships relationship
            JOIN policy_documents related
              ON related.policy_id = CASE
                  WHEN relationship.policy_id = %s THEN relationship.related_policy_id
                  ELSE relationship.policy_id
              END
            WHERE relationship.policy_id = %s OR relationship.related_policy_id = %s
            ORDER BY relationship.relationship_strength DESC, related.title
        """, (policy_id, policy_id, policy_id)).fetchall()


@router.get("/api/policies/{policy_id}/controls")
def policy_controls(policy_id: int, _: dict = Depends(current_user)):
    with shared_policy_connection() as connection:
        policy = connection.execute(
            "SELECT policy_id FROM policy_documents WHERE policy_id = %s",
            (policy_id,),
        ).fetchone()
        if not policy:
            raise HTTPException(status_code=404, detail="Policy document not found")
        return connection.execute("""
            SELECT control.control_id, control.policy_id, document.library_policy_id,
                   control.policy_code, control.policy_name, control.control_sequence,
                   control.control_name, control.control_owner, control.clause_number,
                   control.control_type, control.automation, control.frequency,
                   control.effectiveness, control.status, control.last_tested,
                   control.failures_90d, control.control_description,
                   control.assessment
            FROM policy_controls control
            JOIN policy_documents document ON document.policy_id = control.policy_id
            WHERE control.policy_id = %s
            ORDER BY control.control_sequence
        """, (policy_id,)).fetchall()


@router.post("/api/policy-copilot/chat")
def policy_copilot_chat(payload: PolicyCopilotRequest, user: dict = Depends(current_user)):
    if not MISTRAL_API_KEY:
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY is not configured")
    with shared_policy_connection() as connection:
        configuration = connection.execute("""
            SELECT mistral_agent_id, mistral_library_id
            FROM policy_ai_configuration WHERE id = 1
        """).fetchone()
        policies = connection.execute("""
            SELECT policy_id, library_policy_id, policy_code, title, file_name,
                   clause_number, policy_type
            FROM policy_documents
            ORDER BY SPLIT_PART(library_policy_id, '.', 1)::INTEGER,
                     SPLIT_PART(library_policy_id, '.', 2)::INTEGER
        """).fetchall()
    if not configuration or not configuration["mistral_agent_id"]:
        raise HTTPException(status_code=503, detail="Mistral Policy Copilot is not configured")
    catalog = "\n".join(
        f"- Policy ID {policy['library_policy_id']}: {policy['title']} | "
        f"file {policy['file_name']} | type {policy['policy_type']}"
        for policy in policies
    )
    prompt = f"""
You are Policy Copilot for a bank credit-policy library. Answer the user's question only from
documents retrieved with the document_library tool. Search the library for every answer, including
follow-up requests such as "explain that in simple terms". If the evidence is insufficient, say so.
Answer questions using any relevant policy in the complete library. Do not limit retrieval to the
policy currently displayed in the user interface.

Policy catalog:
{catalog}

User question: {payload.question}

Return only valid JSON with this structure:
{{"answer":"A clear answer with useful detail and plain language when requested.",
  "citations":[{{"policy_id":"1.1","section":"section or clause",
  "evidence":"brief supporting passage or faithful paraphrase"}}]}}
Every factual answer must include at least one citation. Use only Policy IDs from the catalog.
Do not cite a document unless document_library returned relevant evidence from it.
""".strip()

    try:
        with observe_ai(
            "Policy Intelligence", "policy_copilot", user["user_id"],
            input_payload=prompt,
            retrieved_sources=[policy["file_name"] for policy in policies if policy.get("file_name")],
        ) as telemetry:
            with Mistral(api_key=MISTRAL_API_KEY, timeout_ms=MISTRAL_TIMEOUT_MS) as client:
                if payload.conversation_id:
                    response = client.beta.conversations.append(
                        conversation_id=payload.conversation_id, inputs=prompt, store=True,
                    )
                else:
                    response = client.beta.conversations.start(
                        agent_id=configuration["mistral_agent_id"], inputs=prompt, store=True,
                        metadata={"cpi_user": user["user_id"], "purpose": "policy_copilot"},
                    )
            telemetry["response"] = response
        parsed = _json_object(_response_text(response))
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Policy Copilot request failed: {error}") from error

    policy_by_library_id = {policy["library_policy_id"]: policy for policy in policies}
    citations = []
    for citation in parsed.get("citations", []):
        if not isinstance(citation, dict):
            continue
        library_policy_id = str(citation.get("policy_id", "")).strip()
        source = policy_by_library_id.get(library_policy_id)
        if not source:
            continue
        citations.append({
            "policy_id": library_policy_id,
            "policy_database_id": source["policy_id"],
            "policy_code": source["policy_code"],
            "policy_name": source["title"],
            "file_name": source["file_name"],
            "section": str(citation.get("section") or source["clause_number"]),
            "evidence": str(citation.get("evidence") or "Relevant policy passage retrieved."),
        })
    answer = str(parsed.get("answer", "")).strip()
    if not answer:
        raise HTTPException(status_code=502, detail="Policy Copilot returned an empty answer")
    return {
        "conversation_id": response.conversation_id,
        "answer": answer,
        "citations": citations,
    }
