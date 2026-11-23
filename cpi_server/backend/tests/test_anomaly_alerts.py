import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.http_server import configure_http


class AnomalyAlertTests(unittest.TestCase):
    def test_repeated_login_failures_emit_one_warning_per_window(self):
        app = FastAPI()
        configure_http(app)

        @app.post("/api/auth/login")
        def login():
            raise HTTPException(401)

        with TestClient(app) as client, patch("app.http_server.write_request_error") as audit:
            with self.assertLogs("credit_policy_intelligence", level="WARNING") as logs:
                for _ in range(5):
                    self.assertEqual(client.post("/api/auth/login").status_code, 401)
                for _ in range(2):
                    blocked = client.post("/api/auth/login")
                    self.assertEqual(blocked.status_code, 429)
                    self.assertEqual(blocked.headers["Retry-After"], "60")

        self.assertEqual(audit.call_count, 7)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("CPI_SECURITY_ALERT kind=credential_failures source_ip=testclient count=5", logs.output[0])
