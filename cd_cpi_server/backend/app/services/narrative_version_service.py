"""Persistence helpers for per-section narrative version history."""

from sqlalchemy.orm import Session

from app.models.deal import AuditEntry, Section
from app.models.narrative_version import NarrativeVersion


class NarrativeVersionService:
    @staticmethod
    def latest(db: Session, section_id: str) -> NarrativeVersion | None:
        return (
            db.query(NarrativeVersion)
            .filter(NarrativeVersion.section_id == section_id)
            .order_by(
                NarrativeVersion.created_at.desc(),
                NarrativeVersion.id.desc(),
            )
            .first()
        )

    @staticmethod
    def create(
        db: Session,
        section: Section,
        content: str,
        version_type: str,
        created_by: str,
        parent_version_id: str | None = None,
    ) -> NarrativeVersion:
        latest = NarrativeVersionService.latest(db, section.id)
        if latest and latest.content == content:
            return latest
        version = NarrativeVersion(
            deal_id=section.deal_id,
            section_id=section.id,
            content=content,
            version_type=version_type,
            parent_version_id=(
                parent_version_id
                if parent_version_id is not None
                else latest.id if latest else None
            ),
            created_by=created_by,
        )
        db.add(version)
        db.flush()
        return version

    @staticmethod
    def ensure_current(db: Session, section: Section) -> None:
        """Backfill the pre-feature generated/edit state before it is replaced."""
        if NarrativeVersionService.latest(db, section.id):
            return
        original = section.original_generated_content
        current = section.generated_content
        if original:
            NarrativeVersionService.create(
                db,
                section,
                original,
                "generated",
                "Mistral Agent",
            )
        if current and current != original:
            NarrativeVersionService.create(
                db,
                section,
                current,
                "edited",
                "Analyst",
            )

    @staticmethod
    def list_for_section(
        db: Session,
        deal_id: str,
        section_id: str,
    ) -> list[NarrativeVersion]:
        section = (
            db.query(Section)
            .filter(Section.id == section_id, Section.deal_id == deal_id)
            .first()
        )
        if not section:
            return []
        versions = (
            db.query(NarrativeVersion)
            .filter(
                NarrativeVersion.deal_id == deal_id,
                NarrativeVersion.section_id == section_id,
            )
            .order_by(
                NarrativeVersion.created_at.desc(),
                NarrativeVersion.id.desc(),
            )
            .all()
        )
        if not versions and section.generated_content:
            NarrativeVersionService.ensure_current(db, section)
            db.commit()
            versions = (
                db.query(NarrativeVersion)
                .filter(NarrativeVersion.section_id == section_id)
                .order_by(
                    NarrativeVersion.created_at.desc(),
                    NarrativeVersion.id.desc(),
                )
                .all()
            )
        return versions

    @staticmethod
    def mark_final(
        db: Session,
        deal_id: str,
        section_id: str,
        version_id: str,
    ) -> NarrativeVersion | None:
        section = (
            db.query(Section)
            .filter(Section.id == section_id, Section.deal_id == deal_id)
            .first()
        )
        version = (
            db.query(NarrativeVersion)
            .filter(
                NarrativeVersion.id == version_id,
                NarrativeVersion.deal_id == deal_id,
                NarrativeVersion.section_id == section_id,
            )
            .first()
        )
        if not section or not version:
            return None
        db.query(NarrativeVersion).filter(
            NarrativeVersion.deal_id == deal_id,
            NarrativeVersion.section_id == section_id,
        ).update({NarrativeVersion.is_final: False})
        version.is_final = True
        section.generated_content = version.content
        section.final_generated_content = version.content
        section.state = "ready"
        db.add(
            AuditEntry(
                deal_id=deal_id,
                action="narrative.version_marked_final",
                subject=f"{section.title}: {version.id}",
                user="Analyst",
            )
        )
        db.commit()
        db.refresh(version)
        return version

    @staticmethod
    def delete(
        db: Session,
        deal_id: str,
        section_id: str,
        version_id: str,
    ) -> dict[str, object] | None:
        section = (
            db.query(Section)
            .filter(Section.id == section_id, Section.deal_id == deal_id)
            .first()
        )
        version = (
            db.query(NarrativeVersion)
            .filter(
                NarrativeVersion.id == version_id,
                NarrativeVersion.deal_id == deal_id,
                NarrativeVersion.section_id == section_id,
            )
            .first()
        )
        if not section or not version:
            return None

        latest_before_delete = NarrativeVersionService.latest(db, section_id)
        deleted_was_latest = bool(
            latest_before_delete and latest_before_delete.id == version.id
        )
        deleted_was_final = version.is_final
        db.delete(version)
        db.flush()

        remaining = (
            db.query(NarrativeVersion)
            .filter(NarrativeVersion.section_id == section_id)
            .order_by(
                NarrativeVersion.created_at.desc(),
                NarrativeVersion.id.desc(),
            )
            .all()
        )
        explicit_final = next((item for item in remaining if item.is_final), None)

        if not remaining:
            section.generated_content = None
            section.final_generated_content = None
            section.state = "pending"
        elif deleted_was_final:
            # Removing the explicit final returns the section to latest-as-default.
            section.final_generated_content = None
            section.generated_content = remaining[0].content
        elif deleted_was_latest and not explicit_final:
            section.generated_content = remaining[0].content
        elif explicit_final:
            section.generated_content = explicit_final.content
            section.final_generated_content = explicit_final.content

        db.add(
            AuditEntry(
                deal_id=deal_id,
                action="narrative.version_deleted",
                subject=f"{section.title}: {version_id}",
                user="Analyst",
            )
        )
        db.commit()
        return {
            "deleted": True,
            "deleted_version_id": version_id,
            "remaining_count": len(remaining),
            "current_version_id": (
                explicit_final.id
                if explicit_final
                else remaining[0].id if remaining else None
            ),
            "uses_default_final": explicit_final is None,
        }
