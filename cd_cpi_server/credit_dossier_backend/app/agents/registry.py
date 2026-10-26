"""
Agent Registry — maps section_key → dedicated agent instance.

Each section type has its own agent class with tailored system prompts.
The registry provides a single lookup point for the narrative service.
"""

from __future__ import annotations

import logging

from app.agents.base_agent import BaseSectionAgent
from app.agents.sections import (
    ExecutiveSummaryAgent,
    ClientOverviewAgent,
    RelationshipSummaryAgent,
    IndustryAnalysisAgent,
    FinancialAnalysisAgent,
    RatioAnalysisAgent,
    CashFlowAnalysisAgent,
    QualitativeAssessmentAgent,
    CreditRiskAssessmentAgent,
    FacilityStructureAgent,
    PolicyMappingAgent,
    CollateralSecurityAgent,
    CovenantsConditionsAgent,
    ESGAnalysisAgent,
    KeyRisksMitigantsAgent,
    AppendixAgent,
)

logger = logging.getLogger(__name__)

# ── Registry: section_key → singleton agent instance ─────────────

AGENT_REGISTRY: dict[str, BaseSectionAgent] = {
    "executive_summary": ExecutiveSummaryAgent(),
    "client_overview": ClientOverviewAgent(),
    "relationship_summary": RelationshipSummaryAgent(),
    "industry_analysis": IndustryAnalysisAgent(),
    "financial_analysis": FinancialAnalysisAgent(),
    "ratio_analysis": RatioAnalysisAgent(),
    "cash_flow_analysis": CashFlowAnalysisAgent(),
    "qualitative_assessment": QualitativeAssessmentAgent(),
    "credit_risk_assessment": CreditRiskAssessmentAgent(),
    "facility_structure": FacilityStructureAgent(),
    "policy_mapping": PolicyMappingAgent(),
    "collateral_and_security": CollateralSecurityAgent(),
    "covenants_and_conditions": CovenantsConditionsAgent(),
    "esg_analysis": ESGAnalysisAgent(),
    "key_risks_and_mitigants": KeyRisksMitigantsAgent(),
    "appendix": AppendixAgent(),
}

# Fallback agent for unknown section keys
_fallback_agent = BaseSectionAgent()


def get_agent(section_key: str) -> BaseSectionAgent:
    """
    Get the dedicated agent for a section key.
    Falls back to BaseSectionAgent for unknown keys.
    """
    agent = AGENT_REGISTRY.get(section_key)
    if agent is None:
        logger.warning(f"No dedicated agent for section_key={section_key}, using fallback")
        return _fallback_agent
    return agent
