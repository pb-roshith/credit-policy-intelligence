"""Check workspace-scoped agent IDs using the active Mistral credentials."""
from mistralai.client.errors import SDKError


def agent_exists(client, agent_id):
    try:
        client.beta.agents.get(agent_id=agent_id)
        return True
    except SDKError as error:
        if error.status_code == 404:
            return False
        raise
