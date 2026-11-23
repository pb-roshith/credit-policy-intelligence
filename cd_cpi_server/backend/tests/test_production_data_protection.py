"""Production transport and secret handling regressions without live services."""

import asyncio
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, settings
from app.request_security import install_request_security_middleware
from app.secret_provider import SecretProviderError, load_runtime_secrets
from app.services.mcp_service import _production_http_client


class ProductionDataProtectionTests(unittest.TestCase):
    def test_production_cannot_start_with_cleartext_mcp_or_disabled_masking(self):
        valid = {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://db.example.internal/dossier",
            "MCP_SSE_URL": "https://127.0.0.1:8444/sse",
            "CORS_ALLOWED_ORIGINS": "https://dossier.example.internal",
            "REPORT_MASK_SENSITIVE_DATA": True,
            "_env_file": None,
        }
        self.assertTrue(Settings(**valid).production)
        for name, invalid in (
            ("MCP_SSE_URL", "http://127.0.0.1:8004/sse"),
            ("CORS_ALLOWED_ORIGINS", "http://dossier.example.internal"),
            ("REPORT_MASK_SENSITIVE_DATA", False),
        ):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                Settings(**{**valid, name: invalid})

    def test_production_rejects_http_before_processing_and_prevents_caching(self):
        app = FastAPI()
        install_request_security_middleware(app)
        calls = []

        @app.post("/api/test")
        def test_endpoint():
            calls.append(True)
            return {"ok": True}

        with patch.object(settings, "APP_ENV", "prod"), TestClient(app) as client:
            rejected = client.post("http://testserver/api/test")
            self.assertEqual(rejected.status_code, 403)
            self.assertEqual(calls, [])
            admitted = client.post("https://testserver/api/test")
            self.assertEqual(admitted.status_code, 200)
            self.assertEqual(admitted.headers["cache-control"], "no-store")
            self.assertIn("max-age=", admitted.headers["strict-transport-security"])

    def test_production_dotenv_cannot_override_injected_settings_or_supply_secrets(self):
        injected = {"APP_ENV": "production", "DATABASE_URL": "injected"}
        with patch("app.secret_provider.dotenv_values", return_value={"APP_ENV": "development"}):
            load_runtime_secrets("backend", environ=injected)
        self.assertEqual(injected["APP_ENV"], "production")
        with patch("app.secret_provider.dotenv_values", return_value={"DATABASE_URL": "from file"}):
            with self.assertRaisesRegex(SecretProviderError, "DATABASE_URL"):
                load_runtime_secrets("backend", environ=injected)

    def test_mcp_client_rejects_plaintext_before_transport(self):
        async def request():
            async with _production_http_client() as client:
                with self.assertRaisesRegex(httpx.UnsupportedProtocol, "require HTTPS"):
                    await client.get("http://127.0.0.1:8004/sse")

        asyncio.run(request())
