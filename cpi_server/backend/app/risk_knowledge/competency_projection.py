"""Evidence-backed navigation links used by the policy competency queries."""
from datetime import date
import re
from .policy_ontology import RATINGS


EXPOSURE_METRIC = re.compile(r'exposure|concentration|portfolio_limit', re.I)
COLLATERAL_METRIC = re.compile(r'collateral|\bltv\b|loan.to.value|haircut', re.I)
RATING_FIELDS = {'rating', 'credit_rating', 'borrower_credit_rating', 'internal_rating', 'risk_grade',
                 'risk_rating_change', 'credit_rating_change', 'rating_downgrade', 'sovereign_credit_rating'}
ORDERED_RATING_FIELDS = ('rating', 'credit_rating', 'borrower_credit_rating', 'internal_rating')
RATING_REQUIREMENT = re.compile(
    r'\bminimum (?:credit |borrower |internal |risk )?rating\b|'
    r'\b(?:rated|rating)\s+(?:below|above|of at least|of BBB|of BB|grade)|'
    r'\b(?:investment|speculative|sub.investment)[- ]grade (?:borrowers|counterparties|exposures)\b', re.I)
BREACH_TRIGGER = re.compile(r'\b(?:breach(?:es|ing)?|(?<!not )exceed(?:s|ed|ing)?|above (?:the |this )?limit)\b', re.I)
APPROVAL_LANGUAGE = re.compile(r'\b(?:approv\w*|escalat\w*|concurrence)\b', re.I)
OPTIONAL_EXCEPTION = re.compile(r'\bexceptions?\b.{0,110}\b(?:may be (?:approved|granted|permitted|allowed)|requires? approval)\b', re.I)
LIMIT_EXCEPTION = re.compile(r'\b(?:maximum|capped|limit|shall not exceed|must not exceed)\b[^.!?]*\bunless (?:otherwise )?approved\b', re.I)
NAMED_EXCEPTION_APPROVERS = re.compile(r'\bunless (?:otherwise )?approved by (?:the )?([A-Z]{2,8}(?:\s+and\s+(?:the )?[A-Z]{2,8})*)\b')
COVER_DATE = re.compile(r'(?m)(?:[·|]\s*Effective\s+|^Effective(?: date| from)?\s*[:=]\s*)(\d{4}-\d{2}-\d{2})\b', re.I)
SUBSECTOR_LIST = re.compile(r'primary sub-sectors include (.+?)\. Each sub-sector is subject to individual exposure limits', re.I)
PROPERTY_SCOPE = re.compile(r'^For ([a-z][a-z -]*?) properties, underwriters must\b', re.I)
INDUSTRY_SCOPE = re.compile(r'^For borrowers (?:operating )?in (?:the )?([a-z][a-z &-]{1,60}) industry,\s+', re.I)
CONSTRUCTION_SCOPE = re.compile(r'^\s*(?:(?:for|all|any|each) )?construction loans?\b|\bfor (?:any single|all|each) construction loans?\b', re.I)
CLASS_DERIVATION = re.compile(r'\b(?:this|the) rule is derived from (?:the )?policy class\s*[:=-]?\s*["“]?([\w &/-]{2,100})', re.I)
RULE_CODE = re.compile(r'(?im)^\s*Rule (?:ID|Code)\s*[:=]\s*([A-Z][A-Z0-9_.-]{2,40})\b')
RULE_START = re.compile(r'\b(?:this|the) rule (?:takes effect on|is effective from) (\d{4}-\d{2}-\d{2})\b', re.I)
RULE_END = re.compile(r'\b(?:this|the) rule (?:expires on|is effective through) (\d{4}-\d{2}-\d{2})\b', re.I)
SOURCE_RELATIONSHIP_CANDIDATES = {
    'Policy precedence': re.compile(r'\b(?:more stringent rule prevails|superseded by local regulatory requirements|unless local regulations (?:dictate|impose)|takes precedence over)\b', re.I),
    'Named authority matrix reference': re.compile(r'\b(?:defined in|as set out in|in accordance with) the (?:Delegated )?Authority Matrix\b', re.I),
    'Policy review cadence': re.compile(r'\b(?:policy|standards?|clause)\b[^.!?]{0,120}\b(?:reviewed|review) (?:at least )?(?:annually|quarterly|monthly|semi-annually)\b', re.I),
}


def comparisons(group):
    if group:
        yield from group['conditions']
        for child in group['groups']:
            yield from comparisons(child)


def effective_start(record):
    dates = {}
    for clause in record['source_clauses'][:4]:
        for found in COVER_DATE.findall(clause['source_excerpt']):
            try:
                dates[date.fromisoformat(found).isoformat()] = clause['id']
            except ValueError:
                continue
    if len(dates) == 1:
        return next(iter(dates.items()))
    if not dates and record.get('effective_date'):
        return record['effective_date'], None
    return None, None


def concerns(rule):
    """Index applicability dependencies and rule subjects from cited requirements."""
    text = ' '.join(rule['source_quote'].split())
    metrics = [m['key'] for m in rule.get('metrics', [])]
    evidence = [r['evidence_type'] for r in rule.get('evidence_requirements', [])]
    fields = {c['field'] for c in comparisons(rule.get('conditions'))}
    if fields & RATING_FIELDS or RATING_REQUIREMENT.search(text):
        yield 'RATING_DEPENDENCY', 'Credit rating dependency'
    if re.search(r'\b(?:exposure limit|maximum exposure|exposure cap|concentration limit)\b', text, re.I) or (
            any(b['operator'] in ('LT', 'LTE') and EXPOSURE_METRIC.search(b['metric_key']) for b in rule['thresholds'])
            and not re.search(r'\b(?:approv\w*|escalat\w*)\b', text, re.I)):
        yield 'EXPOSURE_LIMIT', 'Exposure limit'
    if any(COLLATERAL_METRIC.search(s) for s in [*metrics, *evidence]) or re.search(
            r'\b(?:collateral|pledged assets?|security interests?)\b.{0,50}\b(?:must|shall|is required|are required|is eligible|may be accepted)\b|'
            r'\b(?:must|shall|required to)\b.{0,50}\b(?:pledge|value|revalue|perfect|verify|register)\b.{0,35}\bcollateral\b', text, re.I):
        yield 'COLLATERAL_REQUIREMENT', 'Collateral requirement'
    if rule['rule_kind'] == 'EXCEPTION_RULE' or OPTIONAL_EXCEPTION.search(text) or LIMIT_EXCEPTION.search(text):
        yield 'EXCEPTION_PROVISION', 'Exception provision'


def approval_trigger(rule, authority):
    # Identify the trigger and the named authority in one cited sentence.
    name = authority['name'].casefold()
    abbreviations = re.findall(r'\(([A-Z]{2,8})\)|\b([A-Z]{2,8})\b', authority['name'])
    mentions = [name, *(a.casefold() for match in abbreviations for a in match if a)]
    evidence = ' '.join(rule['source_quote'].split()) + ' ' + ' '.join(authority['evidence'].split())
    for sentence in re.split(r'(?<=[.!?])\s+', evidence):
        trigger_text = re.sub(r'\b(?:meet(?:s|ing)?|equal(?:s|ling)?) or exceed\w*\b', '', sentence, flags=re.I)
        if ((BREACH_TRIGGER.search(trigger_text) or LIMIT_EXCEPTION.search(sentence)) and APPROVAL_LANGUAGE.search(sentence)
                and any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', sentence, re.I) for term in mentions)):
            if (re.search(r'\bbreach\w*\b|\bexceeds? (?:the |its |an? )?(?:applicable )?limit\b', sentence, re.I)
                    or LIMIT_EXCEPTION.search(sentence)):
                return 'REQUIRES_APPROVAL_ON_BREACH'
            return 'REQUIRES_APPROVAL_ABOVE_THRESHOLD'
    return None


def exception_approvers(rule):
    text = ' '.join(rule['source_quote'].split())
    if not LIMIT_EXCEPTION.search(text):
        return ()
    match = NAMED_EXCEPTION_APPROVERS.search(text)
    if not match:
        return ()
    return [(code, rule['source_quote']) for code in re.findall(r'[A-Z]{2,8}', match[1])]


def subsectors(text, *, policy_scope=False):
    text = ' '.join(text.split())
    match = (SUBSECTOR_LIST if policy_scope else PROPERTY_SCOPE).search(text)
    if match:
        labels = re.sub(r'\([^()]*\)', '', match[1])
        return [label.strip() for label in re.split(r',|\band\b', labels) if label.strip()]
    return []


def explicit_rule_scope(text):
    text = ' '.join(text.split())
    if not re.match(r'(?:for example|for instance|e\.g\.)', text, re.I):
        if match := INDUSTRY_SCOPE.search(text):
            yield 'Industry', 'APPLIES_TO_INDUSTRY', match[1]
        if CONSTRUCTION_SCOPE.search(text):
            yield 'Product', 'DOCUMENTS_PRODUCT_SCOPE', 'Construction loan'
        for label in subsectors(text):
            yield 'Subsector', 'APPLIES_TO_SUBSECTOR', label


def explicit_policy_class(text):
    if match := CLASS_DERIVATION.search(' '.join(text.split())):
        return match[1].strip().casefold()
    return None


def explicit_rule_code(text):
    if match := RULE_CODE.search(text):
        return match[1].upper()
    return None


def rule_effective_period(text):
    text = ' '.join(text.split())
    start, end = RULE_START.search(text), RULE_END.search(text)
    if not start:
        return None
    try:
        start_date = date.fromisoformat(start[1])
        end_date = date.fromisoformat(end[1]) if end else None
    except ValueError:
        return None
    if end_date and end_date < start_date:
        return None
    return {'start_date': start_date.isoformat(), **({'end_date': end_date.isoformat()} if end_date else {})}


def candidate_relationships(passage):
    for label, pattern in SOURCE_RELATIONSHIP_CANDIDATES.items():
        if match := re.search(pattern.pattern.replace(' ', r'\s+'), passage, pattern.flags):
            left = max(0, match.start() - 90)
            right = min(len(passage), match.end() + 90)
            yield label, passage[left:right]
