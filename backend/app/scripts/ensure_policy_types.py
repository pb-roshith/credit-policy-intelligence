"""Ensure the Policy Library has a primary document for each required policy type."""

from pathlib import Path

from mistralai.client import Mistral

from ..config import MISTRAL_API_KEY, MISTRAL_MANUFACTURING_TIMEOUT_MS, POLICY_OUTPUT_DIR
from ..database import db_connection
from ..manufacture_data.policy_generation_service import (
    _json_object,
    _policy_prompt,
    _render_pdf,
    _response_text,
    _start_conversation,
    _summary_prompt,
    _wait_for_document,
)


EXISTING_TYPE_ASSIGNMENTS = {
    "CP-Wholesale-v4.2::4.1": "Underwriting",
    "CP-Wholesale-v4.2::4.2": "Leverage",
    "CP-Wholesale-v4.2::4.3": "Tenor",
    "CP-Wholesale-v4.2::4.4": "Covenant",
    "CP-Retail-v3.1::3.1": "DSCR",
    "CP-Retail-v3.1::3.2": "LTV",
    "RAF-2026-v1.0::1.1": "Risk Appetite",
    "RAF-2026-v1.0::3.5": "Concentration",
    "RAF-2026-v1.0::4.2": "Country",
    "COL-Std-v2.4::2.1": "Collateral",
    "COL-Std-v2.4::2.2": "Collateral",
    "COL-Std-v2.4::2.3": "Collateral",
    "PRC-v1.7::1.1": "Pricing",
    "PRC-v1.7::1.2": "Pricing",
    "SEC-CRE-v2.0::2.1": "Sector",
    "SEC-CRE-v2.0::2.2": "Industry",
    "DEL-v3.3::3.1": "Delegation",
    "DEL-v3.3::3.2": "Delegation",
    "REG-Basel-IV::A.1": "Regulatory Capital",
    "REG-Basel-IV::A.2": "Regulatory Capital",
    "POL-CR-071": "Special Assets & Recovery",
    "POL-CR-072": "Special Assets & Recovery",
    "POL-CR-073": "Special Assets & Recovery",
    "POL-CR-074": "Special Assets & Recovery",
    "POL-CR-075": "Special Assets & Recovery",
    "POL-CR-076": "Special Assets & Recovery",
    "POL-CR-077": "Special Assets & Recovery",
    "POL-CR-078": "Special Assets & Recovery",
    "POL-FIN-079": "Special Assets & Recovery",
    "POL-CR-080": "Special Assets & Recovery",
    "RAT-v1.0": "Rating",
    "SEC-IND-v1.0": "Industry",
    "RAF-CUR-v1.0": "Currency",
    "RAF-DUR-v1.0": "Duration",
    "RAF-LIQ-v1.0": "Liquidity",
}

SUPPLEMENTAL_POLICIES = [
    {
        "library_id": "8.1", "type": "Rating", "code": "RAT-v1.0", "title": "Credit Rating Standards",
        "category": "Credit Policy", "parent": "RAT-v1.0", "clause": "RAT-1.0",
    },
    {
        "library_id": "10.2", "type": "Industry", "code": "SEC-IND-v1.0", "title": "Industry Risk Assessment Policy",
        "category": "Sector Policy", "parent": "SEC-IND-v1.0", "clause": "IND-1.0",
    },
    {
        "library_id": "14.1", "type": "Currency", "code": "RAF-CUR-v1.0", "title": "Foreign Currency Credit Risk Policy",
        "category": "Risk Appetite Framework", "parent": "RAF-CUR-v1.0", "clause": "CUR-1.0",
    },
    {
        "library_id": "15.1", "type": "Duration", "code": "RAF-DUR-v1.0", "title": "Credit Duration Risk Policy",
        "category": "Risk Appetite Framework", "parent": "RAF-DUR-v1.0", "clause": "DUR-1.0",
    },
    {
        "library_id": "16.1", "type": "Liquidity", "code": "RAF-LIQ-v1.0", "title": "Credit Portfolio Liquidity Policy",
        "category": "Risk Appetite Framework", "parent": "RAF-LIQ-v1.0", "clause": "LIQ-1.0",
    },
]


def ensure_policy_types() -> tuple[int, int]:
    output_directory = POLICY_OUTPUT_DIR
    output_directory.mkdir(parents=True, exist_ok=True)
    with db_connection() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('policy_types'))")
        for policy_code, policy_type in EXISTING_TYPE_ASSIGNMENTS.items():
            updated = connection.execute("""
                UPDATE policy_documents SET policy_type = %s
                WHERE policy_code = %s
            """, (policy_type, policy_code))
            if updated.rowcount != 1:
                raise RuntimeError(f"Existing policy match not found for {policy_type}: {policy_code}")
        config = connection.execute("""
            SELECT mistral_library_id, mistral_agent_id
            FROM policy_ai_configuration WHERE id = 1
        """).fetchone()
        supplemental_count = connection.execute("""
            SELECT COUNT(*) AS count
            FROM policy_documents
            WHERE policy_code = ANY(%s)
        """, ([spec["code"] for spec in SUPPLEMENTAL_POLICIES],)).fetchone()["count"]
    if supplemental_count == len(SUPPLEMENTAL_POLICIES):
        return 0, supplemental_count
    if not config or not config["mistral_library_id"] or not config["mistral_agent_id"]:
        raise RuntimeError("Mistral policy library and agent are not configured")

    created = 0
    skipped = 0
    with Mistral(api_key=MISTRAL_API_KEY, timeout_ms=MISTRAL_MANUFACTURING_TIMEOUT_MS) as client:
        library_documents = client.beta.libraries.documents.list(
            library_id=config["mistral_library_id"], page_size=100, page=0
        ).data
        documents_by_name = {document.name: document for document in library_documents}

        for sequence, spec in enumerate(SUPPLEMENTAL_POLICIES, start=1):
            with db_connection() as connection:
                existing = connection.execute(
                    "SELECT policy_id FROM policy_documents WHERE policy_code = %s",
                    (spec["code"],),
                ).fetchone()
            if existing:
                skipped += 1
                continue

            response = _start_conversation(client,
                agent_id=config["mistral_agent_id"],
                inputs=_policy_prompt(
                    spec["parent"], spec["clause"], spec["title"], sequence,
                    total=len(SUPPLEMENTAL_POLICIES),
                ),
                store=False,
            )
            policy_data = _json_object(_response_text(response))
            sections = policy_data.get("sections", [])
            if len(sections) < 10 or any(
                not section.get("heading") or len(section.get("paragraphs", [])) < 4
                for section in sections[:10]
            ):
                raise ValueError(f"Mistral returned incomplete content for {spec['title']}")

            file_name = f"{spec['title']}.pdf"
            pdf_path = output_directory / file_name
            page_count = _render_pdf(
                pdf_path, f"{spec['parent']} Â· {spec['type']}", spec["title"], sections
            )
            if page_count < 10:
                raise ValueError(f"Generated PDF {file_name} has only {page_count} pages")

            uploaded = documents_by_name.get(file_name)
            if not uploaded:
                with pdf_path.open("rb") as pdf_stream:
                    uploaded = client.beta.libraries.documents.upload(
                        library_id=config["mistral_library_id"],
                        file={"file_name": file_name, "content": pdf_stream},
                    )
                documents_by_name[file_name] = uploaded
            _wait_for_document(client, config["mistral_library_id"], uploaded.id)
            summary_response = _start_conversation(client,
                agent_id=config["mistral_agent_id"],
                inputs=_summary_prompt(
                    file_name, spec["parent"], spec["clause"], spec["title"]
                ),
                store=False,
            )
            summary = _response_text(summary_response)
            if len(summary) < 200:
                raise ValueError(f"Mistral returned an incomplete summary for {file_name}")

            with db_connection() as connection:
                display_order = connection.execute(
                    "SELECT COALESCE(MAX(display_order), 0) + 1 AS value FROM policy_documents"
                ).fetchone()["value"]
                connection.execute("""
                    INSERT INTO policy_documents (
                        policy_code, library_policy_id, title, version, policy_category, parent_policy,
                        clause_number, display_order, document_format, source_type, policy_type,
                        effective_date, status, summary, page_count, file_name, local_pdf_path,
                        mistral_document_id, mistral_library_id, mistral_agent_id
                    ) VALUES (%s, %s, %s, '1.0', %s, %s, %s, %s, 'PDF', 'supplemental', %s,
                              CURRENT_DATE, 'Active', %s, %s, %s, %s, %s, %s, %s)
                """, (
                    spec["code"], spec["library_id"], spec["title"], spec["category"], spec["parent"],
                    spec["clause"], display_order, spec["type"], summary, page_count,
                    file_name, str(pdf_path), uploaded.id, config["mistral_library_id"],
                    config["mistral_agent_id"],
                ))
            created += 1
            print(f"Completed {created + skipped}/5: {spec['type']} â€” {file_name}", flush=True)
    return created, skipped


if __name__ == "__main__":
    added, existing = ensure_policy_types()
    print(f"Policy type coverage complete: {added} added, {existing} already present")


