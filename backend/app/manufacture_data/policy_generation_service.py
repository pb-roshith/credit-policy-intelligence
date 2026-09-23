import html
import json
from pathlib import Path
import re
import time

from mistralai.client import Mistral
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from ..config import (
    MISTRAL_MANUFACTURING_TIMEOUT_MS, POLICY_DOCUMENT_TIMEOUT_SECONDS,
    POLICY_JOB_TIMEOUT_SECONDS,
)


POLICY_SPECS = [
    {"library_id": "20.1", "type": "Underwriting", "category": "Credit Policy", "parent": "CP-Wholesale-v4.2", "version": "4.2", "clause": "4.1", "name": "Underwriting Standards"},
    {"library_id": "1.1", "type": "Leverage", "category": "Credit Policy", "parent": "CP-Wholesale-v4.2", "version": "4.2", "clause": "4.2", "name": "Leverage Limits"},
    {"library_id": "4.1", "type": "Tenor", "category": "Credit Policy", "parent": "CP-Wholesale-v4.2", "version": "4.2", "clause": "4.3", "name": "Tenor Limits"},
    {"library_id": "5.1", "type": "Covenant", "category": "Credit Policy", "parent": "CP-Wholesale-v4.2", "version": "4.2", "clause": "4.4", "name": "Covenant Package"},
    {"library_id": "12.1", "type": "DSCR", "category": "Credit Policy", "parent": "CP-Retail-v3.1", "version": "3.1", "clause": "3.1", "name": "DSCR Minimums"},
    {"library_id": "11.1", "type": "LTV", "category": "Credit Policy", "parent": "CP-Retail-v3.1", "version": "3.1", "clause": "3.2", "name": "LTV Ceilings"},
    {"library_id": "18.1", "type": "Risk Appetite", "category": "Risk Appetite Framework", "parent": "RAF-2026-v1.0", "version": "1.0", "clause": "1.1", "name": "Enterprise Limits"},
    {"library_id": "13.1", "type": "Concentration", "category": "Risk Appetite Framework", "parent": "RAF-2026-v1.0", "version": "1.0", "clause": "3.5", "name": "Sector Concentration"},
    {"library_id": "9.1", "type": "Country", "category": "Risk Appetite Framework", "parent": "RAF-2026-v1.0", "version": "1.0", "clause": "4.2", "name": "Country Risk"},
    {"library_id": "2.1", "type": "Collateral", "category": "Collateral Standards", "parent": "COL-Std-v2.4", "version": "2.4", "clause": "2.1", "name": "Coverage Ratios"},
    {"library_id": "2.2", "type": "Collateral", "category": "Collateral Standards", "parent": "COL-Std-v2.4", "version": "2.4", "clause": "2.2", "name": "Eligible Collateral"},
    {"library_id": "2.3", "type": "Collateral", "category": "Collateral Standards", "parent": "COL-Std-v2.4", "version": "2.4", "clause": "2.3", "name": "Haircuts"},
    {"library_id": "3.1", "type": "Pricing", "category": "Pricing Policy", "parent": "PRC-v1.7", "version": "1.7", "clause": "1.1", "name": "RAROC Floors"},
    {"library_id": "3.2", "type": "Pricing", "category": "Pricing Policy", "parent": "PRC-v1.7", "version": "1.7", "clause": "1.2", "name": "Spread Grid"},
    {"library_id": "6.1", "type": "Sector", "category": "Sector Policy", "parent": "SEC-CRE-v2.0", "version": "2.0", "clause": "2.1", "name": "CRE Sub-sector Limits"},
    {"library_id": "10.1", "type": "Industry", "category": "Sector Policy", "parent": "SEC-CRE-v2.0", "version": "2.0", "clause": "2.2", "name": "Construction Guidance"},
    {"library_id": "7.1", "type": "Delegation", "category": "Delegation Matrix", "parent": "DEL-v3.3", "version": "3.3", "clause": "3.1", "name": "Approval Authorities"},
    {"library_id": "7.2", "type": "Delegation", "category": "Delegation Matrix", "parent": "DEL-v3.3", "version": "3.3", "clause": "3.2", "name": "Escalation Rules"},
    {"library_id": "17.1", "type": "Regulatory Capital", "category": "Regulatory Guidance", "parent": "REG-Basel-IV", "version": "Basel IV", "clause": "A.1", "name": "RWA Treatment"},
    {"library_id": "17.2", "type": "Regulatory Capital", "category": "Regulatory Guidance", "parent": "REG-Basel-IV", "version": "Basel IV", "clause": "A.2", "name": "Capital Floors"},
    {"library_id": "8.1", "type": "Rating", "category": "Credit Policy", "parent": "RAT-v1.0", "version": "1.0", "clause": "RAT-1.0", "name": "Credit Rating Standards", "code": "RAT-v1.0"},
    {"library_id": "10.2", "type": "Industry", "category": "Sector Policy", "parent": "SEC-IND-v1.0", "version": "1.0", "clause": "IND-1.0", "name": "Industry Risk Assessment Policy", "code": "SEC-IND-v1.0"},
    {"library_id": "14.1", "type": "Currency", "category": "Risk Appetite Framework", "parent": "RAF-CUR-v1.0", "version": "1.0", "clause": "CUR-1.0", "name": "Foreign Currency Credit Risk Policy", "code": "RAF-CUR-v1.0"},
    {"library_id": "15.1", "type": "Duration", "category": "Risk Appetite Framework", "parent": "RAF-DUR-v1.0", "version": "1.0", "clause": "DUR-1.0", "name": "Credit Duration Risk Policy", "code": "RAF-DUR-v1.0"},
    {"library_id": "16.1", "type": "Liquidity", "category": "Risk Appetite Framework", "parent": "RAF-LIQ-v1.0", "version": "1.0", "clause": "LIQ-1.0", "name": "Credit Portfolio Liquidity Policy", "code": "RAF-LIQ-v1.0"},
]

GENERATED_DOCUMENT_COUNT = len(POLICY_SPECS)
IMPORTED_DOCUMENT_COUNT = 10
POLICY_LIBRARY_DOCUMENT_COUNT = GENERATED_DOCUMENT_COUNT + IMPORTED_DOCUMENT_COUNT


def _response_text(response) -> str:
    parts = []
    for output in response.outputs:
        if getattr(output, "type", None) != "message.output":
            continue
        content = output.content
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.append("".join(getattr(chunk, "text", "") for chunk in content))
    return "\n".join(parts).strip()


def _start_conversation(client: Mistral, **arguments):
    """Retry transient Mistral gateway and rate-limit failures."""
    for attempt in range(4):
        try:
            return client.beta.conversations.start(**arguments)
        except Exception as error:
            message = str(error).lower()
            transient = any(marker in message for marker in (
                "status 429", "status 500", "status 502", "status 503", "status 504",
                "connection", "timeout", "temporarily unavailable",
            ))
            if not transient or attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))


def _json_object(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text[text.find("{"):text.rfind("}") + 1]
    return json.loads(candidate)


def _policy_prompt(parent: str, clause: str, title: str, sequence: int, total: int = GENERATED_DOCUMENT_COUNT) -> str:
    return f"""
Create a realistic, internally consistent bank credit policy document for synthetic demonstration data.
Document {sequence} of {total}.
Parent policy: {parent}
Clause and PDF title: {clause} {title}

Return only valid JSON with this shape:
{{"sections":[{{"heading":"...","paragraphs":["...","...","...","..."]}}]}}

Requirements:
- Exactly 10 sections, each covering a distinct aspect such as purpose, scope, governance, underwriting criteria, quantitative limits, approvals, monitoring, exceptions, reporting, and review.
- Each section must contain 4 to 6 substantial paragraphs and 450 to 600 words total so it fills a full PDF page.
- Include concrete thresholds, roles, evidence requirements, escalation paths, controls, and review frequencies.
- Use professional policy language. Make clear that the document is synthetic demonstration data.
- Do not use markdown, tables, or text outside the JSON object.
""".strip()


def _summary_prompt(file_name: str, parent: str, clause: str, title: str) -> str:
    return f"""
Use the document_library tool to read the newly uploaded document named {file_name}.
Summarize only that document ({parent}, clause {clause} {title}). Write 3 concise paragraphs followed by
five bullet points covering scope, mandatory limits, approval authority, monitoring, and exceptions.
Do not mention this instruction or invent facts not found in the document.
""".strip()


def _render_pdf(path: Path, policy_reference: str, title: str, sections: list[dict]) -> int:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PolicyTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, textColor=colors.HexColor("#163544"),
        alignment=TA_CENTER, spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "PolicySection", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=14, leading=18, textColor=colors.HexColor("#0B7485"), spaceAfter=10,
    )
    body_style = ParagraphStyle(
        "PolicyBody", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9, leading=12, textColor=colors.HexColor("#263942"),
        spaceAfter=8, alignment=0,
    )

    def page_frame(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#B6CDD4"))
        canvas.line(0.65 * inch, 0.55 * inch, 7.85 * inch, 0.55 * inch)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#56727C"))
        canvas.drawString(0.65 * inch, 0.35 * inch, f"{policy_reference} | Synthetic policy data")
        canvas.drawRightString(7.85 * inch, 0.35 * inch, f"Page {document.page}")
        canvas.restoreState()

    story = []
    for index, section in enumerate(sections[:10], start=1):
        if index == 1:
            story.extend([
                Paragraph(html.escape(title), title_style),
                Paragraph(html.escape(f"{policy_reference} Â· Effective {time.strftime('%Y-%m-%d')}"), styles["Heading2"]),
                Spacer(1, 8),
            ])
        story.append(Paragraph(html.escape(f"{index}. {section['heading']}"), section_style))
        for paragraph in section["paragraphs"]:
            story.append(Paragraph(html.escape(str(paragraph)), body_style))
        if index < 10:
            story.append(PageBreak())

    document = SimpleDocTemplate(
        str(path), pagesize=LETTER, rightMargin=0.65 * inch, leftMargin=0.65 * inch,
        topMargin=0.55 * inch, bottomMargin=0.7 * inch,
        title=title, author="TCS Credit Policy Intelligence / Mistral Agent",
    )
    document.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return document.page


def _wait_for_document(client: Mistral, library_id: str, document_id: str,
                       cancel_event=None) -> None:
    deadline = time.monotonic() + POLICY_DOCUMENT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Policy generation was cancelled during shutdown")
        status = client.beta.libraries.documents.status(
            library_id=library_id, document_id=document_id
        )
        state = str(status.processing_status).lower()
        if "completed" in state:
            return
        if "failed" in state or "error" in state:
            raise RuntimeError(f"Mistral could not index document {document_id}: {state}")
        time.sleep(2)
    raise TimeoutError(f"Mistral document processing timed out for {document_id}")


def _resources(client: Mistral, db_connection, model: str) -> tuple[str, str]:
    with db_connection() as connection:
        config = connection.execute(
            "SELECT mistral_library_id, mistral_agent_id FROM policy_ai_configuration WHERE id = 1"
        ).fetchone()
    library_id = config["mistral_library_id"] if config else None
    agent_id = config["mistral_agent_id"] if config else None
    if not library_id:
        library = client.beta.libraries.create(
            name="Credit Policy Intelligence Library",
            description="Synthetic bank credit policies generated by the CPI data manufacturing workflow.",
        )
        library_id = library.id
        with db_connection() as connection:
            connection.execute("""
                INSERT INTO policy_ai_configuration (id, mistral_library_id)
                VALUES (1, %s) ON CONFLICT (id) DO UPDATE
                SET mistral_library_id = EXCLUDED.mistral_library_id
            """, (library_id,))
    if not agent_id:
        agent = client.beta.agents.create(
            model=model,
            name="Credit Policy Manufacturing Agent",
            description="Creates synthetic bank credit policies and summarizes documents stored in the policy library.",
            instructions=(
                "Create detailed, coherent synthetic credit policy documents and concise grounded summaries. "
                "Follow requested output formats exactly. When summarizing, always search the attached document library."
            ),
            tools=[{"type": "document_library", "library_ids": [library_id]}],
            completion_args={"temperature": 0.35, "top_p": 0.9, "max_tokens": 12000},
        )
        agent_id = agent.id
        with db_connection() as connection:
            connection.execute(
                "UPDATE policy_ai_configuration SET mistral_agent_id = %s WHERE id = 1",
                (agent_id,),
            )
    return library_id, agent_id


def run_policy_generation(job_id: str, db_connection, api_key: str, output_dir: Path,
                          source_directory: Path,
                          model: str = "mistral-medium-latest", cancel_event=None) -> None:
    try:
        job_deadline = time.monotonic() + POLICY_JOB_TIMEOUT_SECONDS
        output_dir.mkdir(parents=True, exist_ok=True)
        with db_connection() as connection:
            connection.execute("""
                UPDATE policy_generation_jobs
                SET status = 'running', started_at = CURRENT_TIMESTAMP, message = 'Preparing Mistral agent and library'
                WHERE job_id = %s
            """, (job_id,))
        with Mistral(api_key=api_key, timeout_ms=MISTRAL_MANUFACTURING_TIMEOUT_MS) as client:
            library_id, agent_id = _resources(client, db_connection, model)
            completed = 0
            for sequence, spec in enumerate(POLICY_SPECS, start=1):
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("Policy generation was cancelled during shutdown")
                if time.monotonic() >= job_deadline:
                    raise TimeoutError("Policy generation exceeded its overall execution deadline")
                parent = spec["parent"]
                clause = spec["clause"]
                title = spec["name"]
                display_title = f"{clause} {title}"
                file_name = f"{title}.pdf"
                policy_code = spec.get("code", f"{parent}::{clause}")
                with db_connection() as connection:
                    existing = connection.execute(
                        """SELECT policy_id, file_name, local_pdf_path, mistral_document_id
                           FROM policy_documents WHERE policy_code = %s""",
                        (policy_code,),
                    ).fetchone()
                    connection.execute("""
                        UPDATE policy_generation_jobs
                        SET current_policy = %s, message = %s, completed_documents = %s
                        WHERE job_id = %s
                    """, (display_title, f"Generating policy {sequence} of {GENERATED_DOCUMENT_COUNT}", completed, job_id))
                if existing:
                    old_path = Path(existing["local_pdf_path"])
                    new_path = output_dir / file_name
                    if old_path.is_file() and old_path != new_path and not new_path.exists():
                        old_path.rename(new_path)
                    elif not new_path.exists() and old_path.is_file():
                        new_path = old_path
                    if existing["file_name"] != file_name:
                        client.beta.libraries.documents.update(
                            library_id=library_id,
                            document_id=existing["mistral_document_id"],
                            name=file_name,
                        )
                    with db_connection() as connection:
                        connection.execute("""
                            UPDATE policy_documents
                            SET file_name = %s, local_pdf_path = %s, source_type = 'manufactured'
                            WHERE policy_id = %s
                        """, (file_name, str(new_path), existing["policy_id"]))
                    completed += 1
                    continue

                response = _start_conversation(client,
                    agent_id=agent_id,
                    inputs=_policy_prompt(parent, clause, title, sequence),
                    store=False,
                )
                policy_data = _json_object(_response_text(response))
                sections = policy_data.get("sections", [])
                if len(sections) < 10 or any(not section.get("heading") or len(section.get("paragraphs", [])) < 4 for section in sections[:10]):
                    raise ValueError(f"Mistral returned incomplete policy content for {display_title}")

                pdf_path = output_dir / file_name
                page_count = _render_pdf(pdf_path, f"{parent} Â§{clause}", display_title, sections)
                if page_count < 10:
                    raise ValueError(f"Generated PDF {file_name} has only {page_count} pages")
                library_documents = client.beta.libraries.documents.list(
                    library_id=library_id, page_size=100, page=0
                ).data
                uploaded = next(
                    (document for document in library_documents if document.name == file_name), None
                )
                if not uploaded:
                    with pdf_path.open("rb") as pdf_file:
                        uploaded = client.beta.libraries.documents.upload(
                            library_id=library_id,
                            file={"file_name": file_name, "content": pdf_file},
                        )
                _wait_for_document(client, library_id, uploaded.id, cancel_event)
                summary_response = _start_conversation(client,
                    agent_id=agent_id,
                    inputs=_summary_prompt(file_name, parent, clause, title),
                    store=False,
                )
                summary = _response_text(summary_response)
                if len(summary) < 200:
                    raise ValueError(f"Mistral returned an incomplete summary for {display_title}")
                with db_connection() as connection:
                    connection.execute("""
                        INSERT INTO policy_documents (
                            policy_code, library_policy_id, title, version, policy_category, parent_policy,
                            clause_number, display_order, document_format, source_type, policy_type,
                            effective_date, status, summary,
                            page_count, file_name, local_pdf_path, mistral_document_id,
                            mistral_library_id, mistral_agent_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PDF', 'manufactured', %s,
                                  CURRENT_DATE, 'Active', %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        policy_code, spec["library_id"], display_title, spec["version"], spec["category"], parent,
                        clause, sequence, spec["type"], summary, page_count, file_name, str(pdf_path), uploaded.id,
                        library_id, agent_id,
                    ))
                completed += 1
            with db_connection() as connection:
                connection.execute("""
                    UPDATE policy_generation_jobs
                    SET current_policy = 'Policy document folder',
                        message = 'Uploading 10 policy documents',
                        completed_documents = %s
                    WHERE job_id = %s
                """, (GENERATED_DOCUMENT_COUNT, job_id))
            from ..scripts.import_external_policies import import_policies
            imported, skipped = import_policies(
                source_directory, deadline=job_deadline, cancel_event=cancel_event
            )
            if imported + skipped != IMPORTED_DOCUMENT_COUNT:
                raise RuntimeError("The policy document folder did not produce all 10 imported policies")
        # The relationship catalog depends on the complete set of documents, so it
        # must be refreshed before the generation job is reported as completed.
        from ..scripts.map_policy_relationships import map_policy_relationships
        map_policy_relationships()
        with db_connection() as connection:
            connection.execute("""
                UPDATE policy_generation_jobs
                SET status = 'completed', completed_documents = %s, current_policy = NULL,
                    message = '25 policy PDFs and 10 policy documents are stored in the shared Mistral library',
                    finished_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
            """, (POLICY_LIBRARY_DOCUMENT_COUNT, job_id))
    except Exception as error:
        with db_connection() as connection:
            connection.execute("""
                UPDATE policy_generation_jobs
                SET status = 'failed', message = %s, error = %s, finished_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
            """, ("Policy generation failed", str(error)[:2000], job_id))


