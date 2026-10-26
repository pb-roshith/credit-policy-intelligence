"""Local source ingestion. Documents are inert data and never executable prompts."""
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET
from ..config import BASE_DIR, RULE_MAX_FILE_BYTES, POLICY_OUTPUT_DIR, POLICY_SOURCE_DIR
from ..database import shared_policy_connection

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def parse_document(path):
    path=Path(path)
    size=path.stat().st_size
    if not 0<size<=RULE_MAX_FILE_BYTES: raise ValueError('Source file is empty or exceeds the configured size limit')
    kind=path.suffix.lower()
    paragraphs=[]
    if kind=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(path)
        if reader.is_encrypted: raise ValueError('Encrypted PDF cannot be ingested')
        for page_no,page in enumerate(reader.pages,1):
            text=page.extract_text(extraction_mode='plain') or ''
            paragraphs.extend((part.strip(),page_no,False) for part in re.split(r'\n\s*\n|\n(?=\d+(?:\.\d+)*[.) ]|[A-Z][A-Z &]{5,}\n)',text) if part.strip())
    elif kind=='.docx':
        with ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist())>RULE_MAX_FILE_BYTES*5: raise ValueError('DOCX expanded content exceeds limit')
            xml=archive.read('word/document.xml')
            if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml: raise ValueError('Document XML entities are not supported')
            root=ET.fromstring(xml)
            body=root.find('w:body',NS)
            for block in body:
                if block.tag.endswith('}tbl'):
                    # A table row is one source span, retaining column context.
                    headers=None
                    for row in block.findall('w:tr',NS):
                        cells=['\n'.join(''.join(n.text or '' for n in p.findall('.//w:t',NS)) for p in cell.findall('w:p',NS)).strip() for cell in row.findall('w:tc',NS)]
                        text=' | '.join(cells)
                        if text.strip(' |'):
                            if headers is None:headers=text
                            paragraphs.append((text,None,False))
                elif block.tag.endswith('}p'):
                    text=''.join(n.text or '' for n in block.findall('.//w:t',NS)).strip()
                    style=block.find('w:pPr/w:pStyle',NS)
                    heading=style is not None and 'heading' in str(style.attrib).lower()
                    if text:paragraphs.append((text,None,heading))
    elif kind in ('.txt','.text'):
        text=path.read_text(encoding='utf-8-sig')
        paragraphs=[(p.strip(),None,False) for p in re.split(r'\n\s*\n',text) if p.strip()]
    else: raise ValueError('Supported policy files are PDF, DOCX and UTF-8 text')
    if not paragraphs: raise ValueError('No extractable text; scanned PDFs require OCR before ingestion')
    section=None; clause=None; result=[]
    for text,page,heading in paragraphs:
        number=re.match(r'^\s*((?:[A-Z]+[-.]?)?\d+(?:\.\d+)*|[A-Z]\.\d+)[.)\s:-]+',text)
        if number: clause=number.group(1)
        if heading or (len(text)<180 and not re.search(r'[.;!?]$',text) and (number or text.isupper())): section=text
        # Exact excerpt is retained. Split only at paragraphs/newlines, never invent page numbers.
        if len(text)>16000:
            lines=text.splitlines(keepends=True); chunks=[]; buffer=''
            for line in lines:
                if len(line)>16000: raise ValueError('Source paragraph exceeds extraction limit')
                if len(buffer)+len(line)>16000:chunks.append(buffer.strip());buffer=''
                buffer+=line
            if buffer.strip():chunks.append(buffer.strip())
        else: chunks=[text]
        for excerpt in chunks:
            result.append({'sequence':len(result)+1,'section_heading':section,'clause_number':clause,'page_number':page,'source_excerpt':excerpt,'checksum':hashlib.sha256(excerpt.encode()).hexdigest()})
    return result


def ingest_policy(policy_id):
    with shared_policy_connection() as c:
        policy=c.execute('SELECT * FROM policy_documents WHERE policy_id=%s',(policy_id,)).fetchone()
    if not policy: raise ValueError('Policy document not found')
    path=Path(policy['local_pdf_path']).resolve()
    if not path.is_file():
        # Catalogs copied between workspaces retain obsolete absolute paths.
        candidates=[directory / policy['file_name'] for directory in (POLICY_OUTPUT_DIR,POLICY_SOURCE_DIR)]
        path=next((candidate.resolve() for candidate in candidates if candidate.is_file()),path)
    # Only registered local files inside the application source tree are ingested.
    invalid_path=not path.is_relative_to(BASE_DIR.resolve())
    source_bytes=path.read_bytes() if not invalid_path and path.is_file() and path.stat().st_size<=RULE_MAX_FILE_BYTES else None
    checksum=hashlib.sha256(source_bytes).hexdigest() if source_bytes is not None else 'unavailable'
    with shared_policy_connection() as c:
        c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(f'policy-ingest:{policy_id}',))
        c.execute('INSERT INTO inventory_policies(id,code,name) VALUES (%s,%s,%s) ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name',(policy_id,policy['policy_code'],policy['title']))
        version=c.execute('SELECT * FROM policy_versions WHERE policy_id=%s AND version=%s AND checksum=%s',(policy_id,policy['version'],checksum)).fetchone()
        if version:
            doc=c.execute('SELECT * FROM inventory_documents WHERE policy_version_id=%s',(version['id'],)).fetchone()
            if doc and doc['ingestion_status']=='Completed':
                return dict(policy),dict(version),dict(doc),c.execute('SELECT * FROM policy_clauses WHERE document_id=%s ORDER BY sequence',(doc['id'],)).fetchall()
        c.execute('UPDATE policy_versions SET is_current=false WHERE policy_id=%s',(policy_id,))
        version=c.execute("INSERT INTO policy_versions(policy_id,version,effective_date,effective_date_source,checksum) VALUES (%s,%s,%s,'catalog metadata',%s) ON CONFLICT(policy_id,version,checksum) DO UPDATE SET is_current=true RETURNING *",(policy_id,policy['version'],policy['effective_date'],checksum)).fetchone()
        doc=c.execute("INSERT INTO inventory_documents(policy_version_id,source_document_id,file_name,file_type,checksum,ingestion_status) VALUES (%s,%s,%s,%s,%s,'Pending') ON CONFLICT(policy_version_id) DO UPDATE SET ingestion_status='Pending',error=NULL RETURNING *",(version['id'],policy_id,path.name,path.suffix.lower(),checksum)).fetchone()
    try:
        if invalid_path:raise ValueError('Registered source file is outside the backend document directory')
        if source_bytes is None or not 0<len(source_bytes)<=RULE_MAX_FILE_BYTES:
            raise ValueError('Source file is unavailable, empty or exceeds the configured size limit')
        archive_dir=BASE_DIR / 'inventory_sources'
        archive_dir.mkdir(exist_ok=True)
        snapshot=archive_dir / (checksum+path.suffix.lower())
        if not snapshot.exists():
            from uuid import uuid4
            temporary=archive_dir / (checksum+'.'+uuid4().hex+'.tmp')
            temporary.write_bytes(source_bytes)
            temporary.replace(snapshot)
        elif hashlib.sha256(snapshot.read_bytes()).hexdigest()!=checksum:
            raise ValueError('Archived policy checksum does not match')
        clauses=parse_document(snapshot)
        source_text='\n'.join(cl['source_excerpt'] for cl in clauses)
        import json
        stated={}
        for key,pattern in (('policy_id',r'(?im)^policy(?: id| code)\s*[:=-]\s*([^\n|]+)'),('policy_name',r'(?im)^policy(?: name| title)\s*[:=-]\s*([^\n|]+)'),('policy_version',r'(?im)^(?:policy )?version\s*[:=-]?\s*([A-Za-z0-9][A-Za-z0-9. _-]{0,40})')):
            match=re.search(pattern,source_text)
            if match:stated[key]=match.group(1).strip()
        with shared_policy_connection() as c:
            c.execute('UPDATE inventory_documents SET stated_metadata=%s::jsonb WHERE id=%s',(json.dumps(stated),doc['id']))
        effective_match=re.search(r'(?im)^\s*(?:policy )?effective(?: from| date)?\s*[:=|]\s*([^\n|]+)',source_text)
        if not effective_match:
            effective_match=re.search(r'(?i)effective(?: from| date)?\s*[:=-]?\s*(\d{4}-\d{2}-\d{2})',source_text)
        if effective_match:
            from datetime import datetime
            stated['effective_date']=effective_match.group(1).strip()
            stated_date=None
            for date_format in ('%Y-%m-%d','%d %B %Y','%d %b %Y','%B %d, %Y','%b %d, %Y','%d-%b-%Y'):
                try:stated_date=datetime.strptime(stated['effective_date'],date_format).date();break
                except ValueError:continue
            with shared_policy_connection() as c:
                c.execute('UPDATE inventory_documents SET stated_metadata=%s::jsonb WHERE id=%s',(json.dumps(stated),doc['id']))
                if stated_date:
                    c.execute("UPDATE policy_versions SET effective_date=%s,effective_date_source='source document' WHERE id=%s",(stated_date,version['id']))
                    version['effective_date']=stated_date
                else:
                    c.execute("UPDATE policy_versions SET effective_date_source='Unparsed stated date; catalog fallback requires review' WHERE id=%s",(version['id'],))
    
    except Exception as error:
        with shared_policy_connection() as c:
            c.execute("UPDATE inventory_documents SET ingestion_status='Failed',error=%s,ingested_at=CURRENT_TIMESTAMP WHERE id=%s",(type(error).__name__+': '+str(error)[:300],doc['id']))
        raise
    with shared_policy_connection() as c:
        for clause in clauses:
            c.execute('INSERT INTO policy_clauses(policy_version_id,document_id,sequence,section_heading,clause_number,page_number,source_excerpt,checksum) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(document_id,sequence) DO NOTHING',(version['id'],doc['id'],clause['sequence'],clause['section_heading'],clause['clause_number'],clause['page_number'],clause['source_excerpt'],clause['checksum']))
        doc=c.execute("UPDATE inventory_documents SET ingestion_status='Completed',error=NULL,ingested_at=CURRENT_TIMESTAMP,source_path=%s WHERE id=%s RETURNING *",(str(snapshot),doc['id'])).fetchone()
        rows=c.execute('SELECT * FROM policy_clauses WHERE document_id=%s ORDER BY sequence',(doc['id'],)).fetchall()
    return dict(policy),dict(version),dict(doc),rows

def reconcile_policy_sources():
    """Invalidate an ingested source version when registered file bytes change."""
    with shared_policy_connection() as c:
        rows=c.execute('SELECT pv.id,pv.checksum,pv.policy_id,p.local_pdf_path,p.file_name,p.version,pv.version AS source_version FROM policy_versions pv JOIN policy_documents p ON p.policy_id=pv.policy_id WHERE pv.is_current').fetchall()
    for row in rows:
        path=Path(row['local_pdf_path']).resolve()
        if not path.is_file():
            path=next((candidate.resolve() for folder in (POLICY_OUTPUT_DIR,POLICY_SOURCE_DIR) if (candidate:=folder/row['file_name']).is_file()),path)
        same=False
        if path.is_relative_to(BASE_DIR.resolve()) and path.is_file() and path.stat().st_size<=RULE_MAX_FILE_BYTES:
            same=hashlib.sha256(path.read_bytes()).hexdigest()==row['checksum'] and row['version']==row['source_version']
        if not same:
            with shared_policy_connection() as c:
                changed=c.execute('UPDATE policy_versions SET is_current=false WHERE id=%s AND is_current RETURNING id',(row['id'],)).fetchone()
                if changed:
                    import json
                    c.execute("INSERT INTO audit_events(entity_type,entity_id,previous_value,new_value,action,actor,reason) VALUES ('PolicyVersion',%s,%s::jsonb,%s::jsonb,'source changed','system','Registered policy version or file checksum changed; extraction and business review required')",(str(row['id']),json.dumps({'is_current':True,'checksum':row['checksum']}),json.dumps({'is_current':False})))
