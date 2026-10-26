"""Hosted read-only agent; records follow the verified user's role and ownership."""
import json
import logging
from mistralai.client import Mistral
from mistralai.client.models import FunctionResultEntry
from sqlalchemy import text
from app.config import settings
from app.database import SessionLocal
from app.models.shared_deal_agent import SharedDealAgent
from app.models.deal import Deal
from .new_deal_agent import public_shared_deal
from .mistral_resources import agent_exists

logger = logging.getLogger(__name__)


def ensure_retrieval_agent(db, client):
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('shared_deal_retrieval_agent'))"))
    agent = db.query(SharedDealAgent).filter_by(key="deal_retrieval").first()
    if agent and agent_exists(client, agent.agent_id):
        return agent.agent_id
    hosted = client.beta.agents.create(
        name="Credit Dossier Deal Retrieval Agent", model=settings.MISTRAL_AGENT_MODEL,
        description="Read-only retrieval of authorized Credit Dossier deals for CPI.",
        instructions=("Always call list_owned_deals once to retrieve the current user's authorized deals. "
                      "The server returns all deals to credit analysts and owned deals to relationship managers. "
                      "Never infer or request another user. "
                      "You cannot create, update or delete deals. After the tool returns, report its count "
                      "briefly. Never fabricate deals, amounts, currencies or IDs."),
        tools=[{"type": "function", "function": {
            "name": "list_owned_deals", "description": "Retrieve Credit Dossier deals authorized for the verified signed-in user's role.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        }}], completion_args={"temperature": 0.1, "max_tokens": 512},
    )
    if agent:
        agent.agent_id = hosted.id
    else:
        db.add(SharedDealAgent(key="deal_retrieval", agent_id=hosted.id))
    db.flush()
    return hosted.id


def owned_records(db, user):
    query = db.query(Deal)
    if user.role == "relationship_manager":
        query = query.filter_by(owner_user_id=user.id)
    elif user.role != "credit_analyst":
        return []
    rows = query.order_by(Deal.created_at.desc()).all()
    return [public_shared_deal(deal) for deal in rows]


def retrieve_owned_deals(db, user):
    records = None
    try:
        with Mistral(api_key=settings.MISTRAL_API_KEY, timeout_ms=settings.NEW_DEAL_AGENT_TIMEOUT_MS) as client:
            with SessionLocal() as config_db:
                agent_id = ensure_retrieval_agent(config_db, client)
                config_db.commit()
            response = client.beta.conversations.start(
                agent_id=agent_id, inputs="Retrieve my current Credit Dossier deals for display in CPI.", store=True,
            )
            calls = [entry for entry in response.outputs if getattr(entry, "type", None) == "function.call"]
            if len(calls) != 1 or calls[0].name != "list_owned_deals" or json.loads(calls[0].arguments) != {}:
                raise RuntimeError("Retrieval agent did not request its allowed read-only tool.")
            records = owned_records(db, user)
            client.beta.conversations.append(conversation_id=response.conversation_id, inputs=[
                FunctionResultEntry(tool_call_id=calls[0].tool_call_id,
                                    result=json.dumps({"count": len(records), "deal_ids": [deal["id"] for deal in records]})),
            ])
            return {"deals": records, "status": "agent", "agent_id": agent_id,
                    "conversation_id": response.conversation_id, "source": "Credit Dossier"}
    except Exception:
        logger.warning("Retrieval agent unavailable; returning authorized Dossier records", exc_info=True)
        return {"deals": records if records is not None else owned_records(db, user),
                "status": "direct", "source": "Credit Dossier"}
