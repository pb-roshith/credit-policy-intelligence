"""Load service configuration and keep production secrets out of .env files."""
from __future__ import annotations
import os
from pathlib import Path
from typing import MutableMapping
from dotenv import dotenv_values

PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})
SECRET_NAMES = frozenset({
    "DATABASE_URL", "MCP_DATABASE_URL", "POSTGRES_PASSWORD", "MISTRAL_API_KEY",
    "GEMINI_API_KEY", "SHARED_DEAL_API_KEY", "REPORT_TOKENIZATION_KEY",
    "INITIAL_RELATIONSHIP_MANAGER_PASSWORD", "INITIAL_CREDIT_ANALYST_PASSWORD",
    "INITIAL_ADMIN_PASSWORD",
})

class SecretProviderError(RuntimeError):
    pass

def is_production(environment: str | None) -> bool:
    return (environment or "").strip().casefold() in PRODUCTION_ENVIRONMENTS

def load_runtime_secrets(namespace: str, *, environment: str | None = None,
                         environ: MutableMapping[str, str] | None = None,
                         vault_client=None) -> int:
    """Use injected settings in preference to files in production."""
    backend = Path(__file__).resolve().parents[1]
    paths = {"backend": [backend / ".env"],
             "mcp": [backend / ".env", backend.parent / "mcp" / ".env"]}
    if namespace not in paths:
        raise SecretProviderError(f"Unknown service namespace: {namespace!r}")
    target = os.environ if environ is None else environ
    values = {}
    for path in paths[namespace]:
        values.update({name: value for name, value in dotenv_values(path).items() if value is not None})
    if is_production(environment or target.get("APP_ENV") or values.get("APP_ENV")):
        plaintext = sorted(name for name in SECRET_NAMES if values.get(name))
        if plaintext:
            raise SecretProviderError(
                "Remove production secrets from the service .env files: " + ", ".join(plaintext)
            )
        for name, value in values.items():
            target.setdefault(name, value)
    else:
        target.update(values)
    return len(values)
