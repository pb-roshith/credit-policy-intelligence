"""Server-side access control list for CPI roles."""

from types import MappingProxyType


WORKSPACE_EXECUTION_PERMISSIONS = frozenset({
    "compliance.execute", "decision.execute", "policy.extraction.execute",
})


ROLE_PERMISSIONS = MappingProxyType({
    "admin": frozenset({
        "admin.manage", "workspace.access", "policy.create", "policy.update", "policy.review", "knowledge.review",
        "credit_data.read", "credit_data.create", "credit_data.update", "exceptions.read",
    }) | WORKSPACE_EXECUTION_PERMISSIONS,
    "credit_analyst": frozenset({
        "workspace.access", "accounts.cross_account", "portfolio.access",
        "policy.create", "policy.update", "policy.review", "knowledge.review", "exceptions.read", "exceptions.update",
        "exceptions.delete", "exceptions.approve",
        "credit_data.read", "credit_data.create", "credit_data.update",
    }) | WORKSPACE_EXECUTION_PERMISSIONS,
    "relationship_manager": frozenset({
        "workspace.access", "exceptions.read", "exceptions.create", "exceptions.update", "exceptions.delete",
        "credit_data.read", "credit_data.create", "credit_data.update",
        "policy.create", "policy.update",
    }) | WORKSPACE_EXECUTION_PERMISSIONS,
})


def has_permission(user: dict, permission: str) -> bool:
    """Check a permission against the role obtained from the server-side session."""
    return permission in ROLE_PERMISSIONS.get(user.get("role"), ())
