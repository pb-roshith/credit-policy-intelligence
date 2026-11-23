"""
Database seeding — creates initial demo deals if the DB is empty.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.deal import Deal, Section, AuditEntry
from app.services.deal_service import DEFAULT_SECTIONS

logger = logging.getLogger(__name__)

SEED_DEALS = [
    {
        "id": "deal_kbtz6my",
        "customer": "Ujwal Industries Pvt Ltd",
        "customer_type": "Existing",
        "industry": "Auto Components",
        "segment": "Mid Corporate",
        "geography": "Pune, India",
        "city": "Pune, India",
        "sector": "Auto Components",
        "kyc": "verified",
        "facility": "Term Loan",
        "currency": "INR",
        "amount": 250_000_000,
        "tenure": 60,
        "pricing": "Repo + 285 bps",
        "repayment": "Equated quarterly",
        "collateral": True,
        "due": "2026-06-24",
        "owner": "Analyst",
        "status": "In Progress",
    },
    {
        "id": "deal_a6j7i94",
        "customer": "Vistara Logistics LLP",
        "customer_type": "New-to-bank",
        "industry": "Transportation",
        "segment": "Mid Corporate",
        "geography": "Mumbai, India",
        "city": "Mumbai, India",
        "sector": "Transportation",
        "kyc": "verified",
        "facility": "Working Capital",
        "currency": "INR",
        "amount": 120_000_000,
        "tenure": 12,
        "pricing": "MCLR + 200 bps",
        "repayment": "On demand",
        "collateral": False,
        "due": "2026-06-28",
        "owner": "Analyst",
        "status": "Draft",
    },
    {
        "id": "deal_8jzwj4l",
        "customer": "GreenLeaf Agritech Ltd",
        "customer_type": "Existing",
        "industry": "Agri Processing",
        "segment": "Large Corporate",
        "geography": "Indore, India",
        "city": "Indore, India",
        "sector": "Agri Processing",
        "kyc": "verified",
        "facility": "Syndicated Loan",
        "currency": "INR",
        "amount": 850_000_000,
        "tenure": 84,
        "pricing": "Repo + 310 bps",
        "repayment": "Bullet",
        "collateral": True,
        "due": "2026-07-02",
        "owner": "Analyst",
        "status": "In Review",
    },
]


def seed_if_empty():
    """Seed the database with demo deals if no deals exist."""
    db = SessionLocal()
    try:
        count = db.query(Deal).count()
        if count > 0:
            logger.info(f"Database already has {count} deals — skipping seed.")
            return

        logger.info("Seeding database with demo deals…")
        now = datetime.now(timezone.utc)

        for deal_data in SEED_DEALS:
            deal = Deal(**deal_data, created_at=now, updated_at=now)
            db.add(deal)

            # Create sections
            for idx, sec_def in enumerate(DEFAULT_SECTIONS):
                section = Section(
                    id=f"{deal_data['id']}_{sec_def['section_key']}",
                    deal_id=deal_data["id"],
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
                deal_id=deal_data["id"],
                action="deal.created",
                subject=deal_data["customer"],
                user="System (Seed)",
                created_at=now,
            )
            db.add(audit)

        db.commit()
        logger.info(f"Seeded {len(SEED_DEALS)} demo deals.")
    except SQLAlchemyError:
        logger.exception("Database failure while seeding demo deals.")
        db.rollback()
    finally:
        db.close()
