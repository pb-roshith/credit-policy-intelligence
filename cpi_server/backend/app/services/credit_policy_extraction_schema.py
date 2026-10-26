"""Public extraction contract supplied by the business; proposals only."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class ContractModel(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False,strict=True,str_strip_whitespace=True)

class InputDataField(ContractModel):
    field_name: str = Field(min_length=1,max_length=200,pattern=r'^[A-Za-z][A-Za-z0-9_.]*$')
    definition: str | None = None
    unit: str | None = None
    required: bool = True

class ApplicabilityCondition(ContractModel):
    attribute: str = Field(min_length=1,max_length=200,pattern=r'^[A-Za-z][A-Za-z0-9_.]*$')
    operator: str = Field(min_length=1,max_length=40)
    value: str = Field(max_length=2000)

class AtomicRuleProposal(ContractModel):
    proposed_rule_code: str = Field(min_length=1,max_length=200)
    rule_name: str = Field(min_length=1,max_length=200)
    rule_description: str = Field(min_length=1,max_length=4000)
    mandatory: bool | None = None
    source_section: str | None = None
    source_clause: str = Field(min_length=1,max_length=200)
    source_page: int | None = Field(default=None,ge=1)
    source_excerpt: str = Field(min_length=1,max_length=16000)
    check_question: str = Field(min_length=1,max_length=2000)
    metric_name: str | None = None
    metric_definition: str | None = None
    operator: Literal['EQ','NE','GT','GTE','LT','LTE','BETWEEN','IN','NOT_IN','EXISTS','NOT_EXISTS','MANUAL_ASSESSMENT'] | None = None
    threshold_value: float | str | bool | list[float | str] | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    threshold_unit: str | None = None
    threshold_type: Literal['HARD_LIMIT','WARNING','TARGET'] | None = None
    calculation_logic: str | None = Field(default=None,max_length=2000)
    input_data_fields: list[InputDataField] = Field(default_factory=list,max_length=40)
    data_sources: list[str] = Field(default_factory=list,max_length=30)
    evidence_requirements: list[str] = Field(default_factory=list,max_length=30)
    applicability_conditions: list[ApplicabilityCondition] = Field(default_factory=list,max_length=30)
    applicable_stages: list[str] = Field(default_factory=list,max_length=30)
    severity: Literal['CRITICAL','HIGH','MEDIUM','LOW'] | None = None
    breach_consequence: str | None = None
    exception_allowed: Literal['YES','NO','NOT_STATED'] = 'NOT_STATED'
    approval_or_escalation_requirement: str | None = None
    related_rule_codes: list[str] = Field(default_factory=list,max_length=30)
    relationship_logic: Literal['AND','OR','INDEPENDENT'] | None = None
    extraction_confidence: float = Field(ge=0,le=1)
    ambiguities: list[str] = Field(default_factory=list,max_length=50)
    requires_human_review: Literal[True] = True
    proposed_status: Literal['DRAFT'] = 'DRAFT'

    @model_validator(mode='after')
    def bounds(self):
        if self.lower_bound is not None and self.upper_bound is not None and self.lower_bound>self.upper_bound:
            raise ValueError('Lower bound must not exceed upper bound')
        return self

class NonRuleContent(ContractModel):
    source_clause: str = Field(min_length=1,max_length=200)
    classification: Literal['DEFINITION','GUIDANCE','BACKGROUND','EXAMPLE','OTHER']
    reason_not_extracted: str = Field(min_length=1,max_length=2000)

class CreditPolicyExtractionReport(ContractModel):
    policy_id: str = Field(min_length=1,max_length=128)
    policy_version: str | None = None
    source_document_id: str = Field(min_length=1,max_length=128)
    extraction_run_id: str = Field(min_length=1,max_length=128)
    rules: list[AtomicRuleProposal] = Field(max_length=80)
    non_rule_content: list[NonRuleContent] = Field(default_factory=list,max_length=100)
    processing_warnings: list[str] = Field(default_factory=list,max_length=100)
