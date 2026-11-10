"""Provision the persistent hosted agent, without creating a customer deal."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai_provider import AIClient as Mistral
from app.config import settings
from app.database import Base, engine, SessionLocal
import app.models  # Register the canonical deal and agent tables.
from app.migrations import prepare_database_schemas, apply_additive_migrations
from app.services.new_deal_agent import ensure_agent
from app.services.deal_retrieval_agent import ensure_retrieval_agent


def main():
    prepare_database_schemas(engine)
    Base.metadata.create_all(engine)
    apply_additive_migrations(engine)
    with Mistral(api_key=settings.MISTRAL_API_KEY, timeout_ms=settings.NEW_DEAL_AGENT_TIMEOUT_MS) as client:
        with SessionLocal() as db:
            agent_id = ensure_agent(db, client)
            db.commit()
        print(f"Shared New Deal agent ready: {agent_id}")
        with SessionLocal() as db:
            retrieval_id = ensure_retrieval_agent(db, client)
            db.commit()
        print(f"Read-only Deal Retrieval agent ready: {retrieval_id}")


if __name__ == "__main__":
    main()
