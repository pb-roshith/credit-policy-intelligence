"""Section agent modules — one dedicated agent class per section type."""

from app.agents.sections.executive_summary import ExecutiveSummaryAgent
from app.agents.sections.client_overview import ClientOverviewAgent
from app.agents.sections.relationship_summary import RelationshipSummaryAgent
from app.agents.sections.industry_analysis import IndustryAnalysisAgent
from app.agents.sections.financial_analysis import FinancialAnalysisAgent
from app.agents.sections.ratio_analysis import RatioAnalysisAgent
from app.agents.sections.cash_flow_analysis import CashFlowAnalysisAgent
from app.agents.sections.qualitative_assessment import QualitativeAssessmentAgent
from app.agents.sections.credit_risk_assessment import CreditRiskAssessmentAgent
from app.agents.sections.facility_structure import FacilityStructureAgent
from app.agents.sections.policy_mapping import PolicyMappingAgent
from app.agents.sections.collateral_and_security import CollateralSecurityAgent
from app.agents.sections.covenants_and_conditions import CovenantsConditionsAgent
from app.agents.sections.esg_analysis import ESGAnalysisAgent
from app.agents.sections.key_risks_and_mitigants import KeyRisksMitigantsAgent
from app.agents.sections.appendix import AppendixAgent

__all__ = [
    "ExecutiveSummaryAgent",
    "ClientOverviewAgent",
    "RelationshipSummaryAgent",
    "IndustryAnalysisAgent",
    "FinancialAnalysisAgent",
    "RatioAnalysisAgent",
    "CashFlowAnalysisAgent",
    "QualitativeAssessmentAgent",
    "CreditRiskAssessmentAgent",
    "FacilityStructureAgent",
    "PolicyMappingAgent",
    "CollateralSecurityAgent",
    "CovenantsConditionsAgent",
    "ESGAnalysisAgent",
    "KeyRisksMitigantsAgent",
    "AppendixAgent",
]
