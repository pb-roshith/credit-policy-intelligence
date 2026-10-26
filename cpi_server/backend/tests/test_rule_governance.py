import unittest
from fastapi import HTTPException
from pydantic import ValidationError
from app.routers.rules import RuleDefinition, RuleInput, reviewer

class GovernanceValidationTests(unittest.TestCase):
    def definition(self, **changes):
        data = dict(name="Limit",check="Check exposure",metric="exposure",operator="<=",threshold=100,stage_applicable="All",data_source="request",evidence_requirements="Exposure",source_evidence="Policy limit",change_rationale="Initial draft")
        data.update(changes)
        return data
    def test_reviewer_access(self):
        reviewer({"role":"credit_analyst"})
        with self.assertRaises(HTTPException):
            reviewer({"role":"relationship_manager"})
    def test_arbitrary_calculation_rejected(self):
        with self.assertRaises(ValidationError):
            RuleDefinition(**self.definition(calculation_logic="eval(request)"))
    def test_unknown_metric_rejected(self):
        with self.assertRaises(ValidationError):
            RuleDefinition(**self.definition(metric="invented_metric"))
    def test_invalid_dates_rejected(self):
        with self.assertRaises(ValidationError):
            RuleInput(policy_id=1,definition=self.definition(),effective_from="2026-10-13",effective_to="2026-10-12")
    def test_infinite_threshold_rejected(self):
        with self.assertRaises(ValidationError):
            RuleDefinition(**self.definition(threshold=float("inf")))
