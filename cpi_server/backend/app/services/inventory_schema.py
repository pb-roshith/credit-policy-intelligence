from __future__ import annotations
from datetime import date
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

OPERATORS = Literal['equals','not_equals','greater_than','greater_than_or_equal','less_than','less_than_or_equal','between','in_list','not_in_list','exists','does_not_exist']

class InventoryModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Condition(InventoryModel):
    field: str | None = Field(default=None, pattern=r'^[A-Za-z][A-Za-z0-9_.]*$')
    operator: OPERATORS | None = None
    value: Any = None
    all: list[Condition] | None = Field(default=None, max_length=30)
    any: list[Condition] | None = Field(default=None, max_length=30)

    @model_validator(mode='after')
    def shape(self):
        # Empty unused group arrays are equivalent to null; leaf semantics stay strict.
        if self.all == []: self.all = None
        if self.any == []: self.any = None
        groups = int(self.all is not None) + int(self.any is not None)
        if groups:
            if groups != 1 or self.field or self.operator or not (self.all or self.any):
                raise ValueError('Condition must contain one nonempty AND/OR group')
        elif not self.field or not self.operator:
            raise ValueError('Condition requires a field and an operator')
        if self.operator in ('between','in_list','not_in_list') and not isinstance(self.value,list):
            raise ValueError('List comparison requires a list')
        if self.operator == 'between' and len(self.value)!=2:
            raise ValueError('Between requires two bounds')
        if len(str(self.model_dump())) > 20000:
            raise ValueError('Condition is too complex')
        return self

class Calculation(InventoryModel):
    method: Literal['direct','ratio','percentage','date_age','document_presence','approval_authority','compound','manual']
    field: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    as_of_field: str | None = None
    document_key: str | None = None
    condition: Condition | None = None
    @model_validator(mode='after')
    def inputs(self):
        if self.method in ('direct','date_age','approval_authority') and not self.field:
            raise ValueError('Calculation requires a field')
        if self.method in ('ratio','percentage') and (not self.numerator or not self.denominator):
            raise ValueError('Ratio requires numerator and denominator')
        if self.method=='document_presence' and not self.document_key:
            raise ValueError('Document check requires an evidence key')
        if self.method=='compound' and not self.condition:
            raise ValueError('Compound check requires a condition')
        return self

class EvidenceRequirement(InventoryModel):
    key: str = Field(min_length=1,max_length=200)
    description: str = Field(min_length=1,max_length=2000)
    type: Literal['data','document','approval','human']

class Dependency(InventoryModel):
    clause_id: int
    rule_sequence: int = Field(ge=1)
    relationship: Literal['AND','OR']

class ProposedRule(InventoryModel):
    # Identity, version, status and timestamps are assigned by the server.
    clause_id: int
    rule_sequence: int = Field(ge=1,le=1000)
    rule_name: str = Field(min_length=1,max_length=200)
    rule_description: str = Field(min_length=1,max_length=4000)
    source_excerpt: str = Field(min_length=1,max_length=16000)
    requirement_kind: Literal['mandatory','prohibition','guidance','conditional','target','unspecified']
    rule_type: Literal['quantitative','qualitative','documentary','approval','prohibition','manual']
    check_question: str = Field(min_length=1,max_length=2000)
    metric_name: str | None = None
    metric_definition: str | None = None
    operator: OPERATORS | None = None
    threshold_value: float | str | bool | list[float | str] | None = None
    threshold_unit: str | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    threshold_source: str | None = None
    calculation_logic: Calculation | None = None
    input_data_fields: list[str] = Field(max_length=40)
    data_source: str | None = None
    evidence_requirements: list[EvidenceRequirement] = Field(max_length=30)
    applicability_conditions: Condition | None = None
    applicability_exclusions: Condition | None = None
    applicable_stage: list[str] | None = None
    severity: Literal['WARNING','BREACH'] | None = None
    breach_consequence: str | None = None
    exception_allowed: bool | None = None
    approval_or_escalation_requirement: str | None = None
    extraction_confidence: float = Field(ge=0,le=1)
    extraction_notes: str | None = None
    missing_information: list[str] = Field(max_length=50)
    dependencies: list[Dependency] = Field(default_factory=list,max_length=30)
    requirement_category: str | None = None
    mandatory: bool | None = None
    threshold_type: Literal['HARD_LIMIT','WARNING','TARGET'] | None = None
    risk_severity: Literal['CRITICAL','HIGH','MEDIUM','LOW'] | None = None
    source_rule_code: str | None = None
    input_field_definitions: list[dict] = Field(default_factory=list,max_length=40)
    data_sources: list[str] = Field(default_factory=list,max_length=30)
    ambiguities: list[str] = Field(default_factory=list,max_length=100)
    review_label: Literal['Human Review Required','Manual Review Required'] = 'Human Review Required'
    source_calculation_logic: str | None = None
    applicability_unresolved: bool = False
    representation_id: str | None = None
    representation_node_id: str | None = None
    representation_digest: str | None = None
    representation_version: str | None = None
    requirement_digest: str | None = None
    representation_rule_key: str | None = None

    @model_validator(mode='after')
    def bounds(self):
        if self.lower_bound is not None and self.upper_bound is not None and self.lower_bound>self.upper_bound:
            raise ValueError('Invalid threshold bounds')
        return self

class ExtractionOutput(InventoryModel):
    rules: list[ProposedRule] = Field(max_length=80)

class GovernedDefinition(ProposedRule):
    change_rationale: str = Field(min_length=1,max_length=2000)

class GovernedRuleInput(InventoryModel):
    policy_id: int
    definition: GovernedDefinition
    effective_from: date
    effective_to: date | None = None
    @model_validator(mode='after')
    def period(self):
        if self.effective_to and self.effective_to<self.effective_from:
            raise ValueError('Effective-to must follow effective-from')
        return self
