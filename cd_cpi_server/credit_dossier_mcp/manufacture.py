"""Manufacture 17 synthetic PDFs, upload them to Mistral, and seed 16 tables."""

from __future__ import annotations

import argparse
import io
import json
import logging
from typing import Callable
from xml.sax.saxutils import escape

from mistralai.client import Mistral
from reportlab import rl_config

# CVE-2020-28463: synthetic PDFs do not retrieve remote or local resources.
# Keep only data: available for any future application-generated image.
rl_config.trustedHosts = ["no-remote-resources.invalid"]
rl_config.trustedSchemes = ["data"]

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    LayoutError,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ai_generator import ManufacturingAgent
from catalog import (
    FINANCIAL_AI_TABLES,
    PDF_FILES,
    TABLE_NAMES,
    build_company_context,
    document_sections,
    document_summary,
    table_seed_rows,
)
from database import (
    get_company,
    init_db,
    list_documents,
    seed_credit_tables,
    update_company_library,
    upsert_company,
    upsert_document,
)
from settings import settings


logger = logging.getLogger("local_mcp.manufacture")
GENERATOR_VERSION = 2
ProgressCallback = Callable[[str, str, int, int, str | None], None]


MAX_TABLE_COLUMNS = 4
MAX_TABLE_CELL_CHARS = 600


def _safe_table_cell(value: object) -> str:
    """Keep AI-generated prose from creating a table row taller than a page."""
    text = " ".join(str(value).split())
    if len(text) > MAX_TABLE_CELL_CHARS:
        text = text[: MAX_TABLE_CELL_CHARS - 1].rstrip() + "…"
    return escape(text)


def _styled_tables(rows: list[list[object]], body_style: object) -> list[Table]:
    """Render wide tables as readable column groups within the PDF frame."""
    column_count = max(len(row) for row in rows)
    # ReportLab frames reserve six points of padding on both sides in addition
    # to the document margins. Staying inside this width avoids LayoutError.
    available_width = A4[0] - 84 - 12
    tables: list[Table] = []
    for start in range(0, column_count, MAX_TABLE_COLUMNS):
        stop = min(start + MAX_TABLE_COLUMNS, column_count)
        chunk_size = stop - start
        cell_style = body_style.clone(f"CreditTableBody{start}")
        cell_style.fontSize = 8.5
        cell_style.leading = 10
        header_style = cell_style.clone(f"CreditTableHeader{start}")
        header_style.textColor = colors.white
        header_style.fontName = "Helvetica-Bold"
        wrapped_rows = [
            [
                Paragraph(
                    _safe_table_cell(
                        (row + [""] * (column_count - len(row)))[column_index]
                    ),
                    header_style if row_index == 0 else cell_style,
                )
                for column_index in range(start, stop)
            ]
            for row_index, row in enumerate(rows)
        ]
        table = Table(
            wrapped_rows,
            repeatRows=1,
            colWidths=[available_width / chunk_size] * chunk_size,
            splitByRow=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003A8C")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9AA6B2")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        tables.append(table)
    return tables


def write_pdf(
    target: io.BytesIO,
    filename: str,
    context: dict[str, object],
    generator: ManufacturingAgent | None = None,
) -> str:
    styles = getSampleStyleSheet()
    if generator:
        document = generator.generate_document(filename, context)
    else:
        document = {
            "title": filename.removesuffix(".pdf").replace("_", " "),
            "document_summary": document_summary(filename, context),
            "sections": [
                {
                    "heading": heading,
                    "paragraphs": paragraphs,
                    "table": rows,
                }
                for heading, paragraphs, rows in document_sections(
                    filename,
                    context,
                )
            ],
        }
    story = [
        Paragraph(
            escape(str(document.get("title") or filename)),
            styles["Title"],
        ),
        Paragraph(escape(str(context["company_name"])), styles["Heading2"]),
        Paragraph(
            "SYNTHETIC DATA — generated for application testing only.",
            styles["Normal"],
        ),
        Spacer(1, 12),
    ]
    sections = document.get("sections")
    if not isinstance(sections, list):
        sections = []
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or f"Section {section_index + 1}")
        story.append(Paragraph(escape(heading), styles["Heading2"]))
        story.append(Spacer(1, 5))
        paragraphs = section.get("paragraphs")
        if not isinstance(paragraphs, list):
            paragraphs = [paragraphs] if paragraphs else []
        for paragraph in paragraphs:
            story.append(Paragraph(escape(str(paragraph)), styles["BodyText"]))
            story.append(Spacer(1, 7))
        rows = section.get("table")
        if rows:
            valid_rows = [
                list(row)
                for row in rows
                if isinstance(row, (list, tuple)) and row
            ] if isinstance(rows, list) else []
            if valid_rows:
                for table in _styled_tables(valid_rows, styles["BodyText"]):
                    story.append(table)
                    story.append(Spacer(1, 6))
                story.append(Spacer(1, 9))
        if section_index and section_index % 2 == 1 and section_index < len(sections) - 1:
            story.append(PageBreak())
    SimpleDocTemplate(
        target,
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=36,
        title=str(document.get("title") or filename),
        author="Credit Dossier Synthetic Data Manufacturer",
    ).build(story)
    return str(document.get("document_summary") or document_summary(filename, context))


def create_pdf_payloads(
    context: dict[str, object],
    generator: ManufacturingAgent | None = None,
    summaries: dict[str, str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, bytes]:
    """Generate all PDFs in memory so no local staging files are retained."""
    payloads: dict[str, bytes] = {}
    for filename in PDF_FILES:
        buffer = io.BytesIO()
        try:
            summary = write_pdf(buffer, filename, context, generator)
        except LayoutError:
            logger.warning(
                "AI layout was too large for %s; using the deterministic document fallback",
                filename,
                exc_info=True,
            )
            buffer = io.BytesIO()
            summary = write_pdf(buffer, filename, context, None)
        if summaries is not None:
            summaries[filename] = summary
        payloads[filename] = buffer.getvalue()
        if progress_callback:
            progress_callback(
                "pdf_generation",
                f"Generated {filename}",
                len(payloads),
                len(PDF_FILES),
                filename,
            )
    return payloads


def _create_library(
    client: Mistral,
    context: dict[str, object],
) -> str:
    library = client.beta.libraries.create(
        name=f"{context['company_name']} Local MCP Library",
        description=(
            "Manufactured synthetic credit documents for local Credit Dossier testing."
        ),
    )
    return library.id


def upload_pdfs_to_mistral(
    company: dict,
    context: dict[str, object],
    pdf_payloads: dict[str, bytes],
    summaries: dict[str, str],
    progress_callback: ProgressCallback | None = None,
) -> tuple[str | None, int, str | None]:
    """Upload missing/outdated PDFs and return library ID, count, and error."""
    if not settings.mistral_api_key:
        return (
            company.get("mistral_library_id"),
            0,
            "MISTRAL_API_KEY is not configured; PDFs could not be uploaded.",
        )

    client = Mistral(api_key=settings.mistral_api_key)
    library_id = company.get("mistral_library_id")
    uploaded_count = 0
    try:
        if not library_id:
            library_id = _create_library(client, context)
            update_company_library(company["id"], library_id)

        existing = {
            doc["document_name"]: doc
            for doc in list_documents(
                str(company["owner_user_id"]),
                str(context["company_name"]),
            )
        }
        for number, (filename, pdf_bytes) in enumerate(
            pdf_payloads.items(), start=1
        ):
            existing_document = existing.get(filename)
            is_current = (
                existing_document
                and existing_document.get("mistral_document_id")
                and int(existing_document.get("generator_version") or 1)
                >= GENERATOR_VERSION
            )
            if is_current:
                upsert_document(
                    company["id"],
                    number,
                    filename,
                    summaries[filename],
                    None,
                    existing_document["mistral_document_id"],
                    "uploaded",
                    GENERATOR_VERSION,
                )
                if progress_callback:
                    progress_callback(
                        "pdf_upload",
                        f"Verified existing upload for {filename}",
                        number,
                        len(PDF_FILES),
                        filename,
                    )
                continue
            if existing_document and existing_document.get("mistral_document_id"):
                try:
                    client.beta.libraries.documents.delete(
                        library_id=library_id,
                        document_id=existing_document["mistral_document_id"],
                    )
                except Exception:
                    logger.warning(
                        "Could not remove outdated Mistral document %s; uploading replacement.",
                        filename,
                        exc_info=True,
                    )
            document = client.beta.libraries.documents.upload(
                library_id=library_id,
                file={
                    "file_name": filename,
                    "content": pdf_bytes,
                    "content_type": "application/pdf",
                },
            )
            upsert_document(
                company["id"],
                number,
                filename,
                summaries[filename],
                None,
                document.id,
                "uploaded",
                GENERATOR_VERSION,
            )
            uploaded_count += 1
            if progress_callback:
                progress_callback(
                    "pdf_upload",
                    f"Uploaded {filename}",
                    number,
                    len(PDF_FILES),
                    filename,
                )
        return library_id, uploaded_count, None
    except Exception as exc:
        logger.exception("Mistral Library upload failed")
        return library_id, uploaded_count, str(exc)


def manufacture_company_data(
    owner_user_id: str,
    company_name: str,
    industry: str,
    geography: str,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, object]:
    """Create or refresh one company's complete local MCP data pack."""
    if not company_name.strip() or not industry.strip() or not geography.strip():
        raise ValueError("company_name, industry, and geography are required.")

    logger.info("Initialising PostgreSQL schema")
    init_db()
    if progress_callback:
        progress_callback("initialization", "PostgreSQL schema ready", 1, 1, None)
    fallback_context = build_company_context(
        company_name.strip(),
        industry.strip(),
        geography.strip(),
    )
    summaries: dict[str, str] = {}
    with ManufacturingAgent() as generator:
        logger.info("Generating detailed shared borrower context")
        context = generator.generate_context(fallback_context)
        if progress_callback:
            progress_callback("context", "Borrower context generated", 1, 1, None)
        company = upsert_company(
            owner_user_id, company_name, industry, geography, context
        )

        logger.info("Generating 17 detailed synthetic PDFs in memory")
        pdf_payloads = create_pdf_payloads(
            context,
            generator,
            summaries,
            progress_callback,
        )

        logger.info("Generating detailed rows for 16 PostgreSQL credit tables")
        rows_by_table = table_seed_rows(context)
        for table_number, table_name in enumerate(FINANCIAL_AI_TABLES, start=1):
            rows_by_table[table_name] = generator.generate_financial_rows(
                table_name,
                context,
                rows_by_table[table_name],
            )
            if progress_callback:
                progress_callback(
                    "table_generation",
                    f"Generated detailed rows for {table_name}",
                    table_number,
                    len(FINANCIAL_AI_TABLES),
                    table_name,
                )
        used_ai_generation = generator.available

    company = get_company(owner_user_id, company_name) or company

    logger.info("Uploading PDFs to Mistral Library")
    library_id, uploaded_count, upload_error = upload_pdfs_to_mistral(
        company,
        context,
        pdf_payloads,
        summaries,
        progress_callback,
    )

    logger.info("Seeding detailed data into 16 PostgreSQL credit tables")
    seeded_tables = 0

    def report_seeded_table(table_name: str, row_count: int) -> None:
        nonlocal seeded_tables
        seeded_tables += 1
        if progress_callback:
            progress_callback(
                "table_seed",
                f"Seeded {table_name} ({row_count} rows)",
                seeded_tables,
                len(TABLE_NAMES),
                table_name,
            )

    seeded_rows = seed_credit_tables(
        company["id"], rows_by_table, report_seeded_table
    )

    return {
        "companyName": company_name,
        "industry": industry,
        "geography": geography,
        "databaseName": settings.postgres_database,
        "mcpUrl": f"http://{settings.mcp_host}:{settings.mcp_port}/sse",
        "pdfCount": len(PDF_FILES),
        "generatedPdfCount": len(pdf_payloads),
        "uploadedPdfCount": uploaded_count,
        "tableCount": len(TABLE_NAMES),
        "seededRowCount": seeded_rows,
        "mistralLibraryId": library_id,
        "uploadError": upload_error,
        "generatorVersion": GENERATOR_VERSION,
        "aiDetailedGeneration": used_ai_generation,
        "syntheticData": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--owner-user-id", required=True)
    parser.add_argument("--industry", required=True)
    parser.add_argument("--geography", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--progress-json", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    def emit_progress(
        phase: str,
        stage: str,
        completed: int,
        total: int,
        item: str | None,
    ) -> None:
        if args.progress_json:
            print(
                json.dumps(
                    {
                        "type": "progress",
                        "phase": phase,
                        "stage": stage,
                        "completed": completed,
                        "total": total,
                        "item": item,
                    }
                ),
                flush=True,
            )

    result = manufacture_company_data(
        args.owner_user_id,
        args.company_name,
        args.industry,
        args.geography,
        emit_progress,
    )
    if args.as_json:
        print(json.dumps(result, default=str))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
