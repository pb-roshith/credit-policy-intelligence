"""Source readers adapted from the existing policy_ingestion module, without DB coupling."""
import hashlib
import json
import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET

import openpyxl
from openpyxl.utils import get_column_letter
from .models import Clause, Concept, Document, Provenance

LABEL = 'SYNTHETIC DEMO DATA - NOT AN ACTUAL BANK POLICY'
MAX_BYTES = 20 * 1024 * 1024


def uid(prefix, value):
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:16]


def safe_archive(blob):
    try:
        with ZipFile(BytesIO(blob)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError('Expanded archive exceeds 100 MB')
    except BadZipFile as error:
        raise ValueError('File is not a valid XLSX or DOCX archive') from error


def parse_schema(name, blob):
    safe_archive(blob)
    workbook = openpyxl.load_workbook(BytesIO(blob), data_only=False, read_only=True)
    digest = hashlib.sha256(blob).hexdigest()
    doc_id = uid('DOC-', digest)
    records, concepts, warnings, raw_sheets = [], [], [], {}
    for sheet in workbook:
        rows = list(sheet.iter_rows(values_only=True))
        # Preserve scratch sheets as source records, never infer relations from layout.
        raw_sheets[sheet.title] = [[v.isoformat() if isinstance(v, (date, datetime)) else v for v in r] for r in rows]
        header_index = next((i for i, row in enumerate(rows[:30]) if 'CRDM Entity' in row and 'CRDM Attribute' in row), None)
        if header_index is None:
            warnings.append(f'{sheet.title}: no attribute table header; retained verbatim as auxiliary source data.')
            continue
        headers = [str(v).strip() if v is not None else '' for v in rows[header_index]]
        col = {v: i for i, v in enumerate(headers) if v}
        entities = {}
        for row_no, row in enumerate(rows[header_index + 1:], header_index + 2):
            record = {h: row[i] for h, i in col.items()}
            entity, attribute = record.get('CRDM Entity'), record.get('CRDM Attribute')
            if not isinstance(entity, str) or not isinstance(attribute, str) or not entity.strip() or not attribute.strip():
                continue
            records.append(record)
            source = Provenance(document_id=doc_id, document_name=name, origin='SOURCE_SCHEMA',
                                passage=json.dumps(record, default=str, ensure_ascii=False),
                                sheet=sheet.title, cell=f'A{row_no}:{get_column_letter(len(headers))}{row_no}', clause=str(row_no))
            entity_id = uid('SCHEMA-', f'{doc_id}|{sheet.title}|{entity}')
            if entity not in entities:
                entities[entity] = entity_id
                concepts.append(Concept(concept_id=entity_id, preferred_name=entity, kind='ENTITY', source=source,
                                        metadata={'entity_class': record.get('FACT/DIM/LKP/Report')}))
            concept_id = uid('FIELD-', f'{doc_id}|{sheet.title}|{row_no}')
            concepts.append(Concept(concept_id=concept_id, preferred_name=attribute,
                                    description=str(record.get('Description') or 'UNKNOWN'), parent_concept=entity_id,
                                    source=source, metadata={'unique_reference': record.get('Unique Reference'),
                                    'key_flag': record.get('PK/FK'), 'source_entity': entity,
                                    'source_review': str(record.get('Modler-Review') or ''),
                                    'source_review_date': str(record.get('Review_date') or ''),
                                    'source_comment': str(record.get('Modeler Comment') or '')}))
    workbook.close()
    if not records:
        raise ValueError('No CRDM Entity / CRDM Attribute table found. Supply an XLSX using those headers.')
    warnings.append('Data types, risk-domain classifications, controlled vocabularies and FK targets are UNKNOWN unless explicitly supplied. PK/FK flags do not identify join targets.')
    document = Document(document_id=doc_id, document_name=name, document_type='schema', format='xlsx', checksum=digest,
                        raw_text=json.dumps(raw_sheets, ensure_ascii=False, default=str),
                        metadata={'attribute_records': len(records), 'entities': sum(c.kind == 'ENTITY' for c in concepts),
                                  'sheets': list(raw_sheets), 'warnings': warnings})
    return document, concepts


def parse_document(name, blob, kind):
    if not blob or len(blob) > MAX_BYTES:
        raise ValueError('File must contain between 1 byte and 20 MB')
    suffix = Path(name).suffix.lower()
    spans = []
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(blob))
        if reader.is_encrypted:
            raise ValueError('Encrypted PDFs are unsupported')
        for page, item in enumerate(reader.pages, 1):
            text = item.extract_text() or ''
            spans.extend((part, page, False) for part in re.split(r'\n\s*\n|\n(?=\d+(?:\.\d+)*[.)]?\s)', text) if part.strip())
    elif suffix == '.docx':
        safe_archive(blob)
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        with ZipFile(BytesIO(blob)) as archive:
            xml = archive.read('word/document.xml')
        if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
            raise ValueError('XML entities are unsupported')
        root = ET.fromstring(xml)
        for paragraph in root.findall('.//w:body//w:p', ns):
            text = ''.join(n.text or '' for n in paragraph.findall('.//w:t', ns))
            style = paragraph.find('w:pPr/w:pStyle', ns)
            if text.strip():
                spans.append((text, None, style is not None and 'heading' in str(style.attrib).lower()))
    elif suffix in ('.txt', '.md', '.markdown'):
        text = blob.decode('utf-8-sig')
        spans = [(p, None, bool(re.match(r'^#{1,6} ', p))) for p in re.split(r'\n\s*\n|\n(?=(?:#{1,6}\s|\d+(?:\.\d+)*[.)]?\s))', text) if p.strip()]
    else:
        raise ValueError('Supported document formats: PDF, DOCX, TXT and Markdown')
    if not spans:
        raise ValueError('No extractable text. Scanned PDFs require OCR before upload.')
    raw_text = '\n\n'.join(p for p, _, _ in spans)
    version_match = re.search(r'^Version:\s*(.+)$', raw_text, re.M)
    effective_match = re.search(r'^Effective date:\s*(\d{4}-\d{2}-\d{2})\s*$', raw_text, re.M)
    effective = effective_match.group(1) if effective_match else None
    if effective:
        date.fromisoformat(effective)
    doc_id = uid('DOC-', hashlib.sha256(blob).hexdigest() + kind)
    document = Document(document_id=doc_id, document_name=name, document_type=kind, format=suffix[1:],
                        checksum=hashlib.sha256(blob).hexdigest(), raw_text=raw_text,
                        version=version_match.group(1) if version_match else 'UNKNOWN', effective_date=effective,
                        synthetic=LABEL in raw_text)
    clauses, section, subsection = [], None, None
    for sequence, (text, page, heading) in enumerate(spans, 1):
        if heading:
            section = text.splitlines()[0]
            subsection = section if section.startswith('###') else None
        number = re.match(r'^\s*(\d+(?:\.\d+)*)(?:[.)]|\s)', text)
        source = Provenance(document_id=doc_id, document_name=name,
                            origin='SYNTHETIC_DEMO' if document.synthetic else 'UPLOADED_DOCUMENT',
                            passage=text, section=section, subsection=subsection, page=page,
                            clause=number.group(1) if number else str(sequence),
                            version=document.version, effective_date=effective)
        clauses.append(Clause(clause_id=uid('CLAUSE-', f'{doc_id}|{sequence}'), document_id=doc_id, raw_text=text, source=source))
    return document, clauses
