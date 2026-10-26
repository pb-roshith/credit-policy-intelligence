"""Short-lived, atomic edit leases for narrative sections."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.deal import Section
from app.models.user import User


class NarrativeLockService:
    @staticmethod
    def acquire(db: Session, deal_id: str, section_id: str, user: User) -> Section:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.NARRATIVE_EDIT_LOCK_MINUTES)
        updated = (
            db.query(Section)
            .filter(
                Section.id == section_id,
                Section.deal_id == deal_id,
                or_(
                    Section.edit_lock_user_id.is_(None),
                    Section.edit_lock_expires_at.is_(None),
                    Section.edit_lock_expires_at <= now,
                    Section.edit_lock_user_id == user.id,
                ),
            )
            .update(
                {
                    Section.edit_lock_user_id: user.id,
                    Section.edit_lock_user_name: user.user_id,
                    Section.edit_lock_expires_at: expires_at,
                },
                synchronize_session=False,
            )
        )
        if updated:
            db.commit()
            return db.query(Section).filter(Section.id == section_id).one()

        db.rollback()
        section = (
            db.query(Section)
            .filter(Section.id == section_id, Section.deal_id == deal_id)
            .first()
        )
        if not section:
            raise HTTPException(status_code=404, detail="Section not found")
        raise HTTPException(
            status_code=409,
            detail=f"This narrative is currently being edited by {section.edit_lock_user_name or 'another user'}.",
        )

    @staticmethod
    def require_owner(db: Session, deal_id: str, section_id: str, user: User) -> Section:
        section = (
            db.query(Section)
            .filter(Section.id == section_id, Section.deal_id == deal_id)
            .with_for_update()
            .first()
        )
        if not section:
            raise HTTPException(status_code=404, detail="Section not found")
        expires_at = section.edit_lock_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if (
            section.edit_lock_user_id != user.id
            or expires_at is None
            or expires_at <= datetime.now(timezone.utc)
        ):
            raise HTTPException(
                status_code=409,
                detail="Acquire the narrative edit lock before saving changes.",
            )
        return section

    @staticmethod
    def release(db: Session, deal_id: str, section_id: str, user: User) -> None:
        (
            db.query(Section)
            .filter(
                Section.id == section_id,
                Section.deal_id == deal_id,
                Section.edit_lock_user_id == user.id,
            )
            .update(
                {
                    Section.edit_lock_user_id: None,
                    Section.edit_lock_user_name: None,
                    Section.edit_lock_expires_at: None,
                },
                synchronize_session=False,
            )
        )
        db.commit()
