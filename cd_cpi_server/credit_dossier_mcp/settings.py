"""Environment-backed settings for the local credit-intelligence MCP."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


MCP_DIR = Path(__file__).resolve().parent
load_dotenv(MCP_DIR.parent / "credit_dossier_backend" / ".env")
load_dotenv(MCP_DIR / ".env", override=True)

BACKEND_DIR = MCP_DIR.parent / "credit_dossier_backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
from app.secret_provider import load_runtime_secrets  # noqa: E402

load_runtime_secrets("mcp")


@dataclass(frozen=True)
class Settings:
    postgres_host: str = os.getenv("POSTGRES_HOST", "127.0.0.1")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_database: str = os.getenv("POSTGRES_DB", "cpi_credit_dossier_mcp")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "root")
    mistral_api_key: str = os.getenv("MISTRAL_API_KEY", "")
    mistral_timeout_ms: int = int(os.getenv("MISTRAL_TIMEOUT_MS", "60000"))
    mcp_host: str = os.getenv("MCP_HOST", "127.0.0.1")
    mcp_port: int = int(os.getenv("MCP_PORT", "8004"))
    mcp_transport: str = os.getenv("MCP_TRANSPORT", "sse")

    def postgres_kwargs(self, database: str | None = None) -> dict[str, object]:
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "dbname": database or self.postgres_database,
            "user": self.postgres_user,
            "password": self.postgres_password,
        }


settings = Settings()
