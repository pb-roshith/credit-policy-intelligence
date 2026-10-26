"""
Deal CRUD service — all deal-related database operations.
"""

from __future__ import annotations

import uuid
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.deal import Deal, Section, AuditEntry, Version
from app.models.library_file import LibraryFile
from app.models.user import User


# ── Default section definitions ────────────────────────────────
DEFAULT_SECTIONS = [
    {"section_key": "executive_summary", "title": "Executive Summary", "description": "Overview of client, facility and recommendation.", "sources": "CRM, LOS, Financial summary, ratings summary", "expected_output": "Concise AI-generated summary with key highlights, deal rationale, and risk view.", "optional": False},
    {"section_key": "client_overview", "title": "Client Overview", "description": "Group, promoters, management, history.", "sources": "CRM, KYC, public filings", "expected_output": "Background on the borrower group and management quality.", "optional": False},
    {"section_key": "relationship_summary", "title": "Relationship Summary", "description": "Wallet share, vintage, behaviour.", "sources": "CRM, transaction history", "expected_output": "Relationship vintage, wallet share trend, conduct.", "optional": False},
    {"section_key": "industry_analysis", "title": "Industry Analysis", "description": "Industry outlook and positioning.", "sources": "Sector reports, ratings notes", "expected_output": "Industry view with cycle, peers, and positioning.", "optional": False},
    {"section_key": "financial_analysis", "title": "Financial Analysis", "description": "Three-year financial trend.", "sources": "Audited financials, MIS", "expected_output": "Revenue, EBITDA, leverage commentary with key drivers.", "optional": False},
    {"section_key": "ratio_analysis", "title": "Ratio Analysis", "description": "Leverage, coverage, liquidity.", "sources": "Computed ratios", "expected_output": "Key ratio table and trend explanation.", "optional": False},
    {"section_key": "cash_flow_analysis", "title": "Cash Flow Analysis", "description": "Operating, investing, financing flows.", "sources": "Cash flow statement, projections", "expected_output": "Quality of cash flows and DSCR view.", "optional": False},
    {"section_key": "qualitative_assessment", "title": "Qualitative Assessment", "description": "Governance, ESG, conduct.", "sources": "RM notes, public information", "expected_output": "Qualitative scorecard summary.", "optional": False},
    {"section_key": "credit_risk_assessment", "title": "Credit Risk Assessment", "description": "Internal rating and risk drivers.", "sources": "Rating model, RWA", "expected_output": "Risk grade with drivers and mitigants.", "optional": False},
    {"section_key": "facility_structure", "title": "Facility Structure", "description": "Limits, sub-limits, conditions.", "sources": "Deal sheet", "expected_output": "Facility structure with terms and conditions.", "optional": False},
    {"section_key": "policy_mapping", "title": "Policy Mapping", "description": "Mapping to credit policy.", "sources": "Credit policy document", "expected_output": "Policy compliance check with deviations.", "optional": False},
    {"section_key": "collateral_and_security", "title": "Collateral and Security", "description": "Collateral, security cover.", "sources": "Valuation report, security pack", "expected_output": "Security details and cover ratios.", "optional": False},
    {"section_key": "covenants_and_conditions", "title": "Covenants and Conditions", "description": "Financial and non-financial covenants.", "sources": "Term sheet", "expected_output": "Covenant schedule with thresholds.", "optional": True},
    {"section_key": "esg_analysis", "title": "ESG Analysis", "description": "ESG considerations.", "sources": "ESG questionnaire", "expected_output": "ESG view and material risks.", "optional": True},
    {"section_key": "key_risks_and_mitigants", "title": "Key Risks and Mitigants", "description": "Top risks with mitigants.", "sources": "Risk register", "expected_output": "Top 5 risks with mitigants.", "optional": True},
    {"section_key": "appendix", "title": "Appendix", "description": "Supporting tables and notes.", "sources": "Workbook", "expected_output": "Supporting appendices.", "optional": True},
]


class DealService:
    """Encapsulates all deal-related DB operations."""

    @staticmethod
    def list_deals(
        db: Session,
        current_user: User,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Deal]:
        query = db.query(Deal).options(
            joinedload(Deal.sections),
            joinedload(Deal.versions),
        )
        if current_user.role == "relationship_manager":
            query = query.filter(Deal.owner_user_id == current_user.id)
        elif current_user.role != "credit_analyst":
            return []
        if status and status != "all":
            query = query.filter(Deal.status == status)
        if search:
            query = query.filter(Deal.customer.ilike(f"%{search}%"))
        return query.order_by(Deal.created_at.desc()).all()

    @staticmethod
    def get_deal(db: Session, deal_id: str) -> Deal | None:
        return (
            db.query(Deal)
            .options(
                joinedload(Deal.sections).joinedload(Section.uploads),
                joinedload(Deal.audit_entries),
                joinedload(Deal.versions),
                joinedload(Deal.library_files),
            )
            .filter(Deal.id == deal_id)
            .first()
        )

    @staticmethod
    def create_deal(db: Session, data: dict, owner_user_id: str) -> Deal:
        deal_id = "deal_" + uuid.uuid4().hex[:24]
        deal = Deal(
            id=deal_id,
            owner_user_id=owner_user_id,
            customer=data["customer"],
            customer_type=data.get("customer_type", "Existing"),
            industry=data.get("industry", ""),
            segment=data.get("segment", "Mid Corporate"),
            geography=data.get("geography", ""),
            city=data.get("geography", ""),
            sector=data.get("industry", ""),
            kyc=data.get("kyc", "pending"),
            facility=data.get("facility", "Term Loan"),
            currency=data.get("currency", "INR"),
            amount=data.get("amount", 0),
            tenure=data.get("tenure", 60),
            pricing=data.get("pricing", ""),
            repayment=data.get("repayment", ""),
            collateral=data.get("collateral", False),
            due=data.get("due", ""),
            intake=data.get("intake"),
            creation_request_id=data.get("creation_request_id"),
            owner="Analyst",
            status="Draft",
        )
        db.add(deal)

        # Create default sections
        for idx, sec_def in enumerate(DEFAULT_SECTIONS):
            section = Section(
                id=f"{deal_id}_{sec_def['section_key']}",
                deal_id=deal_id,
                section_key=sec_def["section_key"],
                title=sec_def["title"],
                description=sec_def["description"],
                sources=sec_def["sources"],
                expected_output=sec_def["expected_output"],
                optional=sec_def["optional"],
                state="pending",
                order_index=idx,
            )
            db.add(section)

        # Audit entry
        audit = AuditEntry(
            deal_id=deal_id,
            action="deal.created",
            subject=data["customer"],
            user="Analyst",
        )
        db.add(audit)

        db.commit()
        db.refresh(deal)
        return deal

    @staticmethod
    def update_deal(db: Session, deal_id: str, data: dict) -> Deal | None:
        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        if not deal:
            return None

        for key, value in data.items():
            if value is not None and hasattr(deal, key):
                setattr(deal, key, value)

        deal.updated_at = datetime.now(timezone.utc)

        # Audit
        audit = AuditEntry(
            deal_id=deal_id,
            action="deal.updated",
            subject=deal.customer,
            user="Analyst",
        )
        db.add(audit)

        db.commit()
        db.refresh(deal)
        return deal

    @staticmethod
    def delete_deal(db: Session, deal_id: str) -> bool:
        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        if not deal:
            return False
        db.delete(deal)
        db.commit()
        return True

    @staticmethod
    def get_section(db: Session, section_id: str) -> Section | None:
        return (
            db.query(Section)
            .options(joinedload(Section.uploads))
            .filter(Section.id == section_id)
            .first()
        )

    @staticmethod
    def update_section(db: Session, section_id: str, data: dict) -> Section | None:
        section = db.query(Section).filter(Section.id == section_id).first()
        if not section:
            return None

        # Fields that can legitimately be set to None (cleared)
        nullable_fields = {
            "custom_instructions", "output_template", "generated_content",
            "moderation_status", "moderation_details",
            "accuracy_score", "accuracy_details",
            "url_scrape_details",
        }

        for key, value in data.items():
            if not hasattr(section, key):
                continue
            # Allow None for nullable fields; skip None for non-nullable fields
            if value is None and key not in nullable_fields:
                continue
            if key == "source_urls" and isinstance(value, list):
                value = json.dumps(value)
            setattr(section, key, value)

        db.commit()
        db.refresh(section)
        return section

    @staticmethod
    def update_deal_status_from_sections(db: Session, deal_id: str) -> None:
        """Recompute deal status based on section readiness."""
        deal = db.query(Deal).options(joinedload(Deal.sections)).filter(Deal.id == deal_id).first()
        if not deal:
            return

        mandatory = [s for s in deal.sections if not s.optional]
        ready_count = sum(1 for s in mandatory if s.state == "ready")

        if ready_count == len(mandatory) and deal.status in ("Draft", "In Progress"):
            deal.status = "In Progress"  # All ready but not yet submitted
        elif ready_count > 0 and deal.status == "Draft":
            deal.status = "In Progress"

        db.commit()

    @staticmethod
    def create_version(
        db: Session, deal_id: str, notes: str, actor_user_id: str
    ) -> Version | None:
        deal = (
            db.query(Deal)
            .options(joinedload(Deal.sections))
            .filter(Deal.id == deal_id)
            .first()
        )
        if not deal:
            return None

        snapshot = {
            "deal": {
                field: getattr(deal, field)
                for field in (
                    "customer", "customer_type", "industry", "segment", "geography",
                    "sector", "kyc", "facility", "currency", "amount", "tenure",
                    "pricing", "repayment", "collateral", "due", "primary_color",
                    "secondary_color", "theme_palette",
                )
            },
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "state": section.state,
                    "order_index": section.order_index,
                    # A submitted deal version freezes the draft currently
                    # shown to the reviewer, independently of any previously
                    # marked-final narrative version.
                    "generated_content": (
                        section.generated_content or section.final_generated_content
                    ),
                    "final_generated_content": (
                        section.generated_content or section.final_generated_content
                    ),
                }
                for section in deal.sections
            ],
        }
        version = Version(
            deal_id=deal_id,
            notes=notes,
            status="submitted",
            snapshot_json=json.dumps(snapshot),
        )
        db.add(version)

        deal.status = "In Review"
        deal.updated_at = datetime.now(timezone.utc)

        audit = AuditEntry(
            deal_id=deal_id,
            action="version.submitted",
            subject=version.id,
            user=actor_user_id,
        )
        db.add(audit)

        db.commit()
        db.refresh(version)
        return version

    @staticmethod
    def approve_version(
        db: Session,
        deal_id: str,
        version_id: str,
        actor_user_id: str,
        comments: str = "",
    ) -> Version | None:
        version = db.query(Version).filter(
            Version.id == version_id,
            Version.deal_id == deal_id,
            Version.status == "submitted",
        ).first()
        if not version:
            return None

        version.status = "approved"
        version.review_comments = comments.strip() or None
        version.reviewed_by = actor_user_id
        version.reviewed_at = datetime.now(timezone.utc)

        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        if deal:
            deal.status = "Approved"
            deal.updated_at = datetime.now(timezone.utc)

        audit = AuditEntry(
            deal_id=deal_id,
            action="version.approved",
            subject=version_id,
            user=actor_user_id,
        )
        db.add(audit)

        db.commit()
        db.refresh(version)
        return version

    @staticmethod
    def deny_version(
        db: Session,
        deal_id: str,
        version_id: str,
        actor_user_id: str,
        comments: str,
    ) -> Version | None:
        version = db.query(Version).filter(
            Version.id == version_id,
            Version.deal_id == deal_id,
            Version.status == "submitted",
        ).first()
        if not version:
            return None

        version.status = "denied"
        version.review_comments = comments.strip()
        version.reviewed_by = actor_user_id
        version.reviewed_at = datetime.now(timezone.utc)

        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        if deal:
            deal.status = "Changes Requested"
            deal.updated_at = datetime.now(timezone.utc)

        db.add(
            AuditEntry(
                deal_id=deal_id,
                action="version.denied",
                subject=version_id,
                user=actor_user_id,
            )
        )
        db.commit()
        db.refresh(version)
        return version
