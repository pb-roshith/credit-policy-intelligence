"""Normalize saved narrative citations and remove leaked search artifacts."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models.deal import Section
from app.models.narrative_version import NarrativeVersion
from app.services.mistral_library_service import (
    clean_generation_artifacts,
    normalize_inline_sources,
    repair_inline_source_markers,
)


def clean(content: str | None) -> str | None:
    if not content:
        return content
    content, _ = clean_generation_artifacts(content)
    content = repair_inline_source_markers(content)
    return normalize_inline_sources(content)


def main() -> None:
    db = SessionLocal()
    updated = 0
    try:
        for section in db.query(Section).all():
            for field in (
                "generated_content",
                "original_generated_content",
                "final_generated_content",
            ):
                current = getattr(section, field)
                normalized = clean(current)
                if normalized != current:
                    setattr(section, field, normalized)
                    updated += 1
        for version in db.query(NarrativeVersion).all():
            normalized = clean(version.content)
            if normalized != version.content:
                version.content = normalized or ""
                updated += 1
        db.commit()
        print(f"Updated {updated} saved narrative field(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
