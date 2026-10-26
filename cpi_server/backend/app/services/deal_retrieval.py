"""View-only consumer of the hosted Credit Dossier retrieval agent."""
from .shared_deals import call_shared_deals


class DealRetrievalAgent:
    def run(self, user):
        return call_shared_deals(user, {}, path="/retrieve")
