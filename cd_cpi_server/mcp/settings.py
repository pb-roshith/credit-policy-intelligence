"""Environment-backed settings for the local credit-intelligence MCP."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = MCP_DIR.parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))
from dm_server.backend.deployment_seed import seed_url

BACKEND_DIR = MCP_DIR.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
from app.secret_provider import is_production, load_runtime_secrets  # noqa: E402
from app.transport import POSTGRES_TLS_OPTIONS  # noqa: E402

_injected_database_url = os.getenv('MCP_DATABASE_URL')
load_runtime_secrets("mcp")
_seed_database_url = seed_url('mcp')


@dataclass(frozen=True)
class Settings:
    production: bool = is_production(os.getenv("APP_ENV"))
    database_url: str = _injected_database_url or _seed_database_url or os.getenv('MCP_DATABASE_URL', '')
    postgres_host: str = os.getenv("POSTGRES_HOST", "127.0.0.1")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_database: str = os.getenv("POSTGRES_DB", "cpi_credit_dossier_mcp")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "root")
    ai_provider: str = os.getenv("AI_PROVIDER", "mistral").strip().lower()
    mistral_api_key: str = os.getenv("GEMINI_API_KEY", "") if os.getenv("AI_PROVIDER", "mistral").strip().lower() == "gemini" else os.getenv("MISTRAL_API_KEY", "")
    mistral_timeout_ms: int = int(os.getenv("MISTRAL_TIMEOUT_MS", "60000"))
    mcp_host: str = os.getenv("MCP_HOST", "127.0.0.1")
    mcp_port: int = int(os.getenv("MCP_PORT", "8004"))
    mcp_transport: str = os.getenv("MCP_TRANSPORT", "sse")

    def __post_init__(self) -> None:
        if self.production and not self.database_url:
            raise ValueError("MCP_DATABASE_URL is required in production.")
        if self.production and self.mcp_host != "127.0.0.1":
            raise ValueError("The production MCP service must bind to IPv4 loopback.")

    def postgres_kwargs(self, database: str | None = None) -> dict[str, object]:
        if self.database_url:
            tls = POSTGRES_TLS_OPTIONS if self.production else {}
            return {"conninfo": self.database_url, **tls}
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "dbname": database or self.postgres_database,
            "user": self.postgres_user,
            "password": self.postgres_password,
        }


settings = Settings()
