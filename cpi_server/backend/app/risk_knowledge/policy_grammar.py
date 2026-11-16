"""Conservative whole-sentence policy grammar. Unmatched words are not discarded."""
import re
from typing import Literal
from pydantic import Field, model_validator
from ..services.inventory_schema import InventoryModel, Condition
from .policy_ontology import METRICS, FACILITIES, DOCUMENTS, SCOPE_FIELDS, RATINGS,SCOPE_VOCABULARIES

GRAMMAR_VERSION = 'policy-grammar-v2'


class RequirementFrame(InventoryModel):
    metric: str | None = None
    operator: Literal['less_than_or_equal','greater_than_or_equal','less_than','greater_than','equals'] = 'equals'
    threshold: float | bool
    unit: str | None = None
    scope: Condition | None = None
    exclusions: Condition | None = None
    document: str | None = None

    @model_validator(mode='after')
    def constrained_vocabulary(self):
        if bool(self.metric) == bool(self.document):
            raise ValueError('A requirement constrains one known metric or requires one known document')
        if self.metric:
            if self.metric not in METRICS or self.unit not in METRICS[self.metric]['units'] or isinstance(self.threshold,bool):
                raise ValueError('Unknown metric, incompatible unit or nonnumeric threshold')
        elif self.document not in DOCUMENTS.values() or self.threshold is not True or self.operator != 'equals' or self.unit:
            raise ValueError('Document requirement must explicitly require a known document')
        def check(condition):
            if not condition: return
            if condition.field and condition.field not in SCOPE_FIELDS:
                raise ValueError('Scope field is not defined in the policy ontology')
            if condition.field in ('rating','borrower_credit_rating') and condition.value not in RATINGS:
                raise ValueError('Unknown rating in scope')
            if condition.field and condition.field not in ('rating','borrower_credit_rating'):
                if condition.operator not in ('equals','not_equals','in_list','not_in_list','exists','does_not_exist'):
                    raise ValueError('Text scope fields do not have a numeric ordering')
                values=condition.value if isinstance(condition.value,list) else [condition.value]
                if condition.operator not in ('exists','does_not_exist') and any(not isinstance(v,str) or not v.strip() for v in values):
                    raise ValueError('Text scope conditions require explicit text values')
                if condition.field=='facility' and any(v not in FACILITIES.values() for v in values):
                    raise ValueError('Facility has no declared ontology binding')
                if condition.field in SCOPE_VOCABULARIES and any(v not in SCOPE_VOCABULARIES[condition.field] for v in values):
                    raise ValueError('Scope value has no declared ontology binding')
            for group in (condition.all,condition.any):
                for child in group or []: check(child)
        check(self.scope); check(self.exclusions)
        return self


def sentence_spans(text):
    """Offsets refer to untouched source text, including PDF line wrapping.

    Decimal points and rating modifiers are not sentence boundaries. Semicolons
    and continuation fragments are retained so qualifiers cannot be dropped.
    """
    start = 0
    for match in re.finditer(r'[.!?](?=\s+[A-Z]|\s*$)', text):
        # Numbered headings such as '1. Scope' are not independent requirements.
        if text[start:match.start()].strip().isdigit(): continue
        end = match.end()
        left = start + len(text[start:end]) - len(text[start:end].lstrip())
        if left < end: yield left,end,text[left:end]
        start=end
    left = start + len(text[start:]) - len(text[start:].lstrip())
    end=len(text.rstrip())
    if left<end: yield left,end,text[left:end]


def condition(field,operator,value):
    return {'field':field,'operator':operator,'value':value}


def join(conditions):
    return conditions[0] if len(conditions)==1 else {'all':conditions} if conditions else None


def normalized_text(source):
    # Restore PDF line wrapping inside a hyphenated word without changing the
    # original quote or character offsets retained by the representation.
    def unwrap(match):
        if match[1].upper()+'-' in RATINGS:return match[0]
        return match[1]+'-'+match[2]
    source=re.sub(r'\b([A-Za-z]+)-[ \t]*\r?\n[ \t]*([a-z]+)',unwrap,source)
    return ' '.join(source.split()).strip()


def parse_ltv_branches(source):
    """Recognize a complete, explicit two-branch ceiling statement.

    Shared subject conditions are copied into EACH branch, then conjoined with
    its own qualifier. No ambiguous mixed product/program matrix is flattened.
    """
    text=normalized_text(source).rstrip('.').lower()
    prefix=None;field=None
    subjects={
        'investment properties':condition('property_type','equals','Investment Property'),
        'secondary or vacation homes':{'any':[condition('property_type','equals','Secondary Residence'),condition('property_type','equals','Vacation Home')]},
        'primary residences':condition('property_type','equals','Primary Residence'),
    }
    patterns=[
        r'(?P<subject>investment properties) are subject to a stricter ltv ceiling of (?P<branches>.+)',
        r'for (?P<subject>secondary or vacation homes|primary residences|investment properties), the maximum ltv is(?: reduced to| set at)? (?P<branches>.+)',
        r'(?P<subject>auto loans) are subject to a maximum ltv of (?P<branches>.+)',
    ]
    match=next((m for p in patterns if (m:=re.fullmatch(p,text))),None)
    if not match:return None
    subject=match['subject']
    prefix=condition('facility','equals','Auto Loan') if subject=='auto loans' else subjects[subject]
    field='vehicle_condition' if subject=='auto loans' else 'loan_program'
    branch=re.fullmatch(r'(\d+(?:\.\d+)?)% for (.+) and (\d+(?:\.\d+)?)% for (.+)',match['branches'])
    if not branch:return None
    frames=[]
    for number,label in ((branch[1],branch[2]),(branch[3],branch[4])):
        choices=[value for value,terms in SCOPE_VOCABULARIES[field].items() if label in terms]
        if len(choices)!=1:return None
        frames.append(RequirementFrame(metric='ltv',operator='less_than_or_equal',threshold=float(number),unit='%',
                                      scope=join([prefix,condition(field,'equals',choices[0])])))
    return frames


def parse_requirements(source):
    frames=parse_ltv_branches(source)
    if frames:return frames,None
    frame,reason=parse_requirement(source)
    return ([frame],None) if frame else ([],reason)


def parse_scope(text):
    text=' '.join(text.lower().split()).strip(' ,')
    if not text or text in ('all borrowers','all requests','all credit requests'):
        return None
    parts=[]
    text=re.sub(r'^all\s+(?=term loans|revolving credit facilities)','',text)
    # This deliberately requires an explicit facility, with an optional rating.
    # 'These limits', omitted subjects and cross-sentence inheritance are unresolved.
    facility=next((v for v in sorted(FACILITIES,key=len,reverse=True) if text==v or text.startswith(v+' ')),None)
    if facility:
        parts.append(condition('facility','equals',FACILITIES[facility]))
        text=text[len(facility):].strip()
        text=re.sub(r'^(?:for|to)\s+','',text)
    if text:
        text=re.sub(r' by a recognized credit rating agency$','',text)
        rating=re.fullmatch(r'borrowers (?:externally )?rated (below|above) ([a-z0-9+-]+)|borrowers (?:externally )?rated ([a-z0-9+-]+) or (higher|lower)',text)
        if not rating: raise ValueError('Unsupported or ambiguous scope')
        if rating.group(1):
            op='less_than' if rating.group(1)=='below' else 'greater_than'; value=rating.group(2).upper()
        else:
            op='greater_than_or_equal' if rating.group(4)=='higher' else 'less_than_or_equal'; value=rating.group(3).upper()
        if value not in RATINGS: raise ValueError('Unknown rating')
        parts.append(condition('borrower_credit_rating',op,value))
    return join(parts)


NUM=r'(?P<number>\d+(?:,\d{3})*(?:\.\d+)?)'
UNIT=r'(?P<unit>x|%|percent|years?|USD|INR|EUR|GBP)'
AMOUNT=NUM+r'\s*'+UNIT
PREFIX=r'(?:(?:the|a)\s+)?'


def parse_requirement(source):
    """Return a fully matched frame or a reason for requiring interpretation."""
    text=normalized_text(source)
    if text.endswith('.'):text=text[:-1]
    # These constructs require an explicit representation; never erase qualifiers.
    if re.search(r'\b(?:unless|except|provided|subject to|however|such as|for example|typically|may|should|these|those|respectively)\b|;',text,re.I):
        return None,'Exception, qualification, guidance or inherited context needs interpretation'
    scope=None
    if text.lower().startswith('for '):
        if ',' not in text:return None,'A scope prefix needs an explicit boundary'
        prefix,text=text[4:].split(',',1)
        try:scope=parse_scope(prefix)
        except ValueError as error:return None,str(error)
        text=text.strip()
    # Document requirements are a distinct executable ontology node.
    document=re.fullmatch(r'(?:the borrower|borrowers|the applicant|applicants) (?:must|shall) (?:provide|submit) (?:an? )?(.+)',text,re.I)
    if document:
        key=DOCUMENTS.get(document.group(1).lower())
        if key:return RequirementFrame(document=key,threshold=True,scope=scope),None
        return None,'Document type is not bound in the policy ontology'
    metric_terms={term:key for key,value in METRICS.items() for term in value['terms']}
    terms='|'.join(re.escape(t) for t in sorted(metric_terms,key=len,reverse=True))
    metric=r'(?P<metric>'+terms+r')'
    # An explicit DSCR formula is understood only for its registered components.
    formula=r'(?:\s*\((?P<formula>[^)]+)\))?'
    patterns=[
        (PREFIX+r'(?P<bound>minimum|maximum) '+metric+formula+r'(?: for (?P<facility>term loans|revolving credit facilities))? (?:is(?: set at| limited to)?|shall be|must be) '+AMOUNT+r'(?: for (?P<suffix>.+))?',None),
        (PREFIX+metric+formula+r' (?:must|shall) (?P<comparison>not exceed|be no more than|be at most|be at least|be no less than|exceed|be below|be greater than|be less than) '+AMOUNT+r'(?: for (?P<suffix>.+))?',None),
        (PREFIX+metric+r' (?:is|are) subject to a (?P<bound>maximum|minimum)(?: of)? '+AMOUNT+r'(?: for (?P<suffix>.+))?',None),
    ]
    for pattern,_ in patterns:
        match=re.fullmatch(pattern,text,re.I)
        if not match:continue
        values=match.groupdict();key=metric_terms[values['metric'].lower()]
        unit=values['unit'];unit='years' if unit.lower() in ('year','years') else '%' if unit.lower()=='percent' else unit.upper() if len(unit)==3 else unit.lower()
        if values.get('formula'):
            expected=METRICS[key].get('formula')
            if not expected or [p.strip().lower() for p in values['formula'].split('/')]!=expected:
                return None,'Formula is not an exact registered calculation'
        extra=[]
        if scope:extra.append(scope)
        for name in ('facility','suffix'):
            if values.get(name):
                try:
                    parsed=parse_scope(values[name])
                    if parsed:extra.append(parsed)
                except ValueError as error:return None,str(error)
        op={'minimum':'greater_than_or_equal','maximum':'less_than_or_equal'}.get(values.get('bound','').lower())
        if not op:
            op={'not exceed':'less_than_or_equal','be no more than':'less_than_or_equal','be at most':'less_than_or_equal',
                'be at least':'greater_than_or_equal','be no less than':'greater_than_or_equal','exceed':'greater_than',
                'be below':'less_than','be greater than':'greater_than','be less than':'less_than'}[values['comparison'].lower()]
        def has_facility(c):
            return bool(c and (c.get('field')=='facility' or any(has_facility(child) for child in c.get('all') or [])))
        if key=='tenor' and not any(has_facility(c) for c in extra):
            return None,'Tenor facility scope may be inherited; explicit interpretation required'
        try:return RequirementFrame(metric=key,operator=op,threshold=float(values['number'].replace(',','')),unit=unit,scope=join(extra)),None
        except ValueError:return None,'Metric or unit has no approved ontology binding'
    return None,'No complete policy grammar pattern matches this passage'


def validate_frame_source(frame,quote):
    """Literal grounding is mandatory even for a human-reviewed interpretation.

    These checks do not claim to prove semantic correctness. They prevent a
    fallback/reviewer from supplying absent limits, units, terms or scope values.
    """
    text=normalized_text(quote).lower()
    if frame.metric:
        metric=METRICS[frame.metric]
        if not any(re.search(r'(?<![a-z])'+re.escape(term)+r'(?![a-z])',text) for term in metric['terms']):
            raise ValueError('Metric terminology is absent from its source passage')
        numbers={float(v.replace(',','')) for v in re.findall(r'(?<![A-Za-z])\d[\d,]*(?:\.\d+)?',quote)}
        if frame.threshold not in numbers:raise ValueError('Threshold is not explicitly stated in the source passage')
        units={'years':r'\byears?\b','x':r'(?<=\d)\s*x\b|\btimes\b','%':r'%|\bpercent\b'}
        if not re.search(units.get(frame.unit,r'\b'+re.escape(frame.unit.lower())+r'\b'),text):
            raise ValueError('Unit is not explicitly stated in the source passage')
        formula=re.search(r'(?:'+ '|'.join(re.escape(term) for term in metric['terms']) +r')\s*\(([^)]+/[^)]+)\)',text)
        if formula and [part.strip() for part in formula.group(1).split('/')]!=metric.get('formula'):
            raise ValueError('Source formula differs from the declared metric binding')
    else:
        labels=[name for name,key in DOCUMENTS.items() if key==frame.document]
        if not any(label in text for label in labels):raise ValueError('Required document is absent from the source passage')
    def check(condition):
        if not condition:return
        if condition.field and condition.operator not in ('exists','does_not_exist'):
            values=condition.value if isinstance(condition.value,list) else [condition.value]
            for value in values:
                if condition.field=='facility':terms=[term for term,canonical in FACILITIES.items() if canonical==value]
                elif condition.field in SCOPE_VOCABULARIES:terms=SCOPE_VOCABULARIES[condition.field].get(value,[])
                else:terms=[str(value).lower()]
                found=any(re.search(r'(?<![a-z0-9+-])'+re.escape(term)+r'(?![a-z0-9+-])',text) for term in terms) if condition.field in ('rating','borrower_credit_rating') else any(term in text for term in terms)
                if not found:raise ValueError('Scope value is absent from the supporting source passage')
        for group in (condition.all,condition.any):
            for child in group or []:check(child)
    check(frame.scope);check(frame.exclusions)


def classify_non_rule(source):
    """Classify structure and bounded purpose/background language, not unknown obligations."""
    text=normalized_text(source)
    lines=[line.strip() for line in source.splitlines() if line.strip()]
    structural=[
        r'(?:\d+[.)]\s*)+',
        r'Version:\s*[A-Za-z0-9][A-Za-z0-9_.-]{0,39}',r'Effective date:\s*\d{4}-\d{2}-\d{2}',
        r'Page \d+(?: of \d+)?',
        r'CP-[A-Za-z0-9_.-]+\s+\u00a7\d+(?:\.\d+)*\s*(?:\|\s*Synthetic policy data|[\u00b7|]\s*Effective\s+\d{4}-\d{2}-\d{2})',
        r'\d+(?:\.\d+)*[.)]?\s+(?:Scope|Purpose|Definitions|Responsibilities|Governance|References|Policy Requirements|LTV Ceilings)',
    ]
    if lines and all(any(re.fullmatch(p,line,re.I) for p in structural) for line in lines):
        return {'category':'DOCUMENT_STRUCTURE','reason':'Document numbering, heading, version or page furniture; original source retained'}
    # Do not turn a purpose-style sentence containing an obligation, numerical
    # requirement, exception or scope exclusion into non-rule content.
    operative=r'\b(?:must|shall|required|require|requires|mandatory|binding|prohibited|permitted|responsible|unless|except|only if|subject to|does not apply|apply to|applies to|at least|at most|above|below|exceed|before|after|monthly|quarterly|annually|retain|retains|retained|independent appraiser)\b|\bto (?:submit|obtain|approve|verify|calculate|provide|collect)\b|%|[$<>\u2264\u2265]|\b\d+(?:\.\d+)?\s*(?:x|years?|months?|days?|USD|INR|EUR|GBP)\b'
    if re.search(operative,text,re.I):return None
    purpose=r'(?:Purpose\s+)?The purpose of (?:this|the) (?:clause|policy|document)\b.+\bis to\b.+'
    background=[
        r'This clause ensures that the bank maintains a prudent balance between\b.+',
        r'By (?:defining|standardizing|adhering to)\b.+',
        r'This synthetic demonstration document is designed to illustrate\b.+',
        r'It provides a realistic example of\b.+',
        r'While the data and scenarios presented are fictional\b.+',
        r'Finally, the purpose of this clause extends to\b.+',
        r'The exception process is designed to balance\b.+',
    ]
    if re.fullmatch(purpose,text,re.I):
        return {'category':'PURPOSE','reason':'Purpose statement retained as policy context; no executable requirement inferred'}
    if any(re.fullmatch(p,text,re.I) for p in background):
        return {'category':'BACKGROUND','reason':'Descriptive background retained as context; no operational test specified'}
    return None


def is_non_rule(text):
    return classify_non_rule(text) is not None
