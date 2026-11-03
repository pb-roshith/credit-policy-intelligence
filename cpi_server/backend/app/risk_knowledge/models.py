from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

TaxonomyStatus = Literal['SOURCE', 'AI_PROPOSED', 'REVIEWED', 'APPROVED', 'REJECTED']
RuleStatus = Literal['CANDIDATE', 'REVIEWED', 'APPROVED', 'REJECTED', 'SUPERSEDED']
CLASSIFICATIONS = ['DEFINITION', 'SCOPE', 'ELIGIBILITY', 'RULE', 'THRESHOLD', 'LIMIT',
                   'REQUIREMENT', 'APPROVAL', 'PROHIBITION', 'EXCEPTION', 'OVERRIDE',
                   'COLLATERAL_REQUIREMENT', 'DOCUMENTATION_REQUIREMENT',
                   'MONITORING_REQUIREMENT', 'REPORTING_REQUIREMENT', 'OTHER']
ClauseCategory = Literal[tuple(CLASSIFICATIONS)]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Provenance(Model):
    document_id: str
    document_name: str
    origin: str
    passage: str
    section: str | None = None
    subsection: str | None = None
    page: int | None = None
    clause: str | None = None
    sheet: str | None = None
    cell: str | None = None
    version: str = 'UNKNOWN'
    effective_date: str | None = None
    provider: str | None = None


class Concept(Model):
    concept_id: str
    preferred_name: str
    description: str = 'UNKNOWN'
    parent_concept: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    source: Provenance
    risk_domain: str = 'UNKNOWN'
    data_type: str = 'UNKNOWN'
    allowed_values: list[str] = Field(default_factory=list)
    status: TaxonomyStatus = 'SOURCE'
    confidence: float | None = None
    review_notes: str = ''
    kind: str = 'ATTRIBUTE'
    metadata: dict[str, Any] = Field(default_factory=dict)


class Relationship(Model):
    relationship_id: str
    subject: str
    predicate: str = Field(pattern=r'^[A-Z][A-Z_]*$')
    object: str
    source: Provenance
    status: TaxonomyStatus = 'AI_PROPOSED'
    confidence: float | None = None
    review_notes: str = ''


class Document(Model):
    document_id: str
    document_name: str
    document_type: Literal['schema', 'reference', 'policy']
    format: str
    checksum: str
    raw_text: str
    version: str = 'UNKNOWN'
    effective_date: str | None = None
    synthetic: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Clause(Model):
    clause_id: str
    document_id: str
    raw_text: str
    source: Provenance
    categories: list[str] = Field(default_factory=lambda: ['OTHER'])
    confidence: float | None = None
    classification_method: str = 'deterministic keywords; not model probability'


class Condition(Model):
    attribute: str
    operator: Literal['=', '!=', '>', '>=', '<', '<=', 'in', 'not_in', 'exists']
    value: Any = None
    unit: str | None = None
    taxonomy_mapping: str | None = None
    original_term: str
    normalized_term: str | None = None


class Expression(Model):
    logic: Literal['AND', 'OR'] = 'AND'
    conditions: list[Condition] = Field(default_factory=list)
    groups: list[Expression] = Field(default_factory=list)


class Outcome(Model):
    action: str = 'UNKNOWN'
    value: Any = None
    authority: str | None = None


class Rule(Model):
    rule_id: str
    rule_name: str
    rule_type: str
    risk_domain: str = 'Credit Risk'
    scope: list[Condition] = Field(default_factory=list)
    conditions: Expression
    logical_expression: str = 'AND'
    outcome: Outcome
    exceptions: list[Expression] = Field(default_factory=list)
    policy: Provenance
    clause_id: str
    ontology_links: list[str] = Field(default_factory=list)
    confidence: float | None = None
    status: RuleStatus = 'CANDIDATE'
    validation: dict[str, bool] = Field(default_factory=dict)
    review_notes: str = ''
    requires_review: bool = True
    synthetic: bool = False


class Review(Model):
    status: str
    reviewer: str = Field(min_length=2, max_length=100)
    notes: str = Field(min_length=3, max_length=4000)


class CreditRequest(Model):
    borrower: str = 'ABC Manufacturing Ltd'
    attributes: dict[str, Any]
    currency: str = 'INR'
    as_of: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')


class Classifications(Model):
    # Publish the allowed values to the model's JSON schema, rather than only
    # rejecting invented categories after generation in a Python validator.
    categories: list[ClauseCategory] = Field(min_length=1,max_length=len(CLASSIFICATIONS))


class ConceptCandidates(Model):
    items: list[Concept]


class RelationshipCandidates(Model):
    items: list[Relationship]


class RuleCandidates(Model):
    items: list[Rule]


class Mapping(Model):
    original_term: str
    concept_id: str | None
    normalized_term: str | None


class Mappings(Model):
    items: list[Mapping]


class ConflictExplanation(Model):
    explanation: str
    requires_review: Literal[True] = True
