"""Load runtime configuration from service .env files."""
from __future__ import annotations
import os
from pathlib import Path
from typing import MutableMapping
from dotenv import dotenv_values

PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod"})

class SecretProviderError(RuntimeError):
    pass

def is_production(environment: str | None) -> bool:
    return (environment or "").strip().casefold() in PRODUCTION_ENVIRONMENTS

def load_runtime_secrets(namespace: str, *, environment: str | None = None,
                         environ: MutableMapping[str, str] | None = None,
                         vault_client=None) -> int:
    """Read .env values without encrypted-store or cloud-provider overrides."""
    backend = Path(__file__).resolve().parents[1]
    paths = {"backend": [backend / ".env"],
             "mcp": [backend / ".env", backend.parent / "credit_dossier_mcp" / ".env"]}
    if namespace not in paths:
        raise SecretProviderError(f"Unknown service namespace: {namespace!r}")
    target = os.environ if environ is None else environ
    values = {}
    for path in paths[namespace]:
        values.update({name: value for name, value in dotenv_values(path).items() if value is not None})
    target.update(values)
    return len(values)
