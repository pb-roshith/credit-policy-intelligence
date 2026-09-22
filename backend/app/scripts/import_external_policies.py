"""Import existing policy documents into the CPI Mistral Library and database."""

import argparse
from pathlib import Path
import time

from mistralai.client import Mistral

from ..config import MISTRAL_API_KEY, MISTRAL_MANUFACTURING_TIMEOUT_MS, POLICY_SOURCE_DIR
from ..database import db_connection
from ..manufacture_data.policy_generation_service import (
    GENERATED_DOCUMENT_COUNT, _response_text, _start_conversation, _wait_for_document,
)


EXTERNAL_POLICIES = [
    ("POL-CR-071", "POL-71", "Delinquency Management Policy", "POL-71_Delinquency_Management_Policy.docx"),
    ("POL-CR-072", "POL-72", "Collections Policy", "POL-72_Collections_Policy.docx"),
    ("POL-CR-073", "POL-73", "Hardship & Forbearance Policy", "POL-73_Hardship_Forbearance_Policy.docx"),
    ("POL-CR-074", "POL-74", "Restructuring & Modification Policy", "POL-74_Restructuring_Modification_Policy.docx"),
    ("POL-CR-075", "POL-75", "Non-Performing Loan (NPL) Policy", "POL-75_Non_Performing_Loan_NPL_Policy.docx"),
    ("POL-CR-076", "POL-76", "Watchlist & Special Mention Policy", "POL-76_Watchlist_Special_Mention_Policy.docx"),
    ("POL-CR-077", "POL-77", "Special Assets Management Policy", "POL-77_Special_Assets_Management_Policy.docx"),
    ("POL-CR-078", "POL-78", "Recovery Policy", "POL-78_Recovery_Policy.docx"),
    ("POL-FIN-079", "POL-79", "Write-Off Policy", "POL-79_Write_Off_Policy.docx"),
    ("POL-CR-080", "POL-80", "Debt Sale Policy", "POL-80_Debt_Sale_Policy.docx"),
]

CATEGORY = "Special Assets & Recovery"
PARENT_POLICY = "Problem Credit Management"


def import_policies(source_directory: Path, deadline: float | None = None,
                    cancel_event=None) -> tuple[int, int]:
    missing = [file_name for _, _, _, file_name in EXTERNAL_POLICIES
               if not (source_directory / file_name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing policy documents: {', '.join(missing)}")

    with db_connection() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('policy_import'))")
        config = connection.execute("""
            SELECT mistral_library_id, mistral_agent_id
            FROM policy_ai_configuration WHERE id = 1
        """).fetchone()
    if not config or not config["mistral_library_id"] or not config["mistral_agent_id"]:
        raise RuntimeError("Generate or configure the Mistral policy library before importing documents")

    imported = 0
    skipped = 0
    with Mistral(api_key=MISTRAL_API_KEY, timeout_ms=MISTRAL_MANUFACTURING_TIMEOUT_MS) as client:
        library_documents = client.beta.libraries.documents.list(
            library_id=config["mistral_library_id"], page_size=100, page=0
        ).data
        documents_by_name = {document.name: document for document in library_documents}

        for import_sequence, (policy_code, policy_number, title, file_name) in enumerate(EXTERNAL_POLICIES, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Policy import was cancelled during shutdown")
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Policy import exceeded the policy job execution deadline")
            offset = GENERATED_DOCUMENT_COUNT + import_sequence
            with db_connection() as connection:
                existing = connection.execute(
                    "SELECT policy_id FROM policy_documents WHERE policy_code = %s",
                    (policy_code,),
                ).fetchone()
            source_path = source_directory / file_name
            uploaded = documents_by_name.get(file_name)
            if not uploaded:
                with source_path.open("rb") as document_stream:
                    uploaded = client.beta.libraries.documents.upload(
                        library_id=config["mistral_library_id"],
                        file={"file_name": file_name, "content": document_stream},
                    )
                documents_by_name[file_name] = uploaded
            _wait_for_document(
                client, config["mistral_library_id"], uploaded.id, cancel_event
            )
            if existing:
                with db_connection() as connection:
                    connection.execute("""
                        UPDATE policy_documents
                        SET file_name = %s, local_pdf_path = %s, mistral_document_id = %s,
                            mistral_library_id = %s, mistral_agent_id = %s,
                            source_type = 'imported'
                        WHERE policy_id = %s
                    """, (file_name, str(source_path), uploaded.id,
                          config["mistral_library_id"], config["mistral_agent_id"],
                          existing["policy_id"]))
                skipped += 1
                continue
            document_info = client.beta.libraries.documents.get(
                library_id=config["mistral_library_id"], document_id=uploaded.id
            )
            page_count = int(getattr(document_info, "number_of_pages", None) or 1)
            summary_response = _start_conversation(client,
                agent_id=config["mistral_agent_id"],
                inputs=(
                    f"Use document_library to read only {file_name}. Summarize {policy_code}, {title}, "
                    "in three concise paragraphs followed by five bullet points covering scope, "
                    "classification or triggers, approvals, monitoring, and exceptions. Ground every "
                    "statement in the document and do not mention this instruction."
                ),
                store=False,
            )
            summary = _response_text(summary_response)
            if len(summary) < 200:
                raise ValueError(f"Mistral returned an incomplete summary for {file_name}")

            with db_connection() as connection:
                connection.execute("""
                    INSERT INTO policy_documents (
                        policy_code, library_policy_id, title, version, policy_category, parent_policy,
                        clause_number, display_order, document_format, source_type, policy_type,
                        effective_date, status, summary, page_count, file_name,
                        local_pdf_path, mistral_document_id, mistral_library_id, mistral_agent_id
                    ) VALUES (%s, %s, %s, '1.0', %s, %s, %s, %s, 'DOCX', 'imported', 'Special Assets & Recovery',
                              CURRENT_DATE, 'Active', %s, %s, %s, %s, %s, %s, %s)
                """, (
                    policy_code, f"19.{import_sequence}", f"{policy_number} {title}", CATEGORY, PARENT_POLICY,
                    policy_number, offset, summary, page_count, file_name, str(source_path),
                    uploaded.id, config["mistral_library_id"], config["mistral_agent_id"],
                ))
            imported += 1
            print(f"Imported {imported + skipped}/10: {file_name}", flush=True)
    return imported, skipped


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source_directory", nargs="?", type=Path,
        default=POLICY_SOURCE_DIR,
    )
    arguments = parser.parse_args()
    created, existing = import_policies(arguments.source_directory.resolve())
    print(f"Import complete: {created} added, {existing} already present")


