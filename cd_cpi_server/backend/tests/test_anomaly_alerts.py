"""Exercise alert thresholds, audit preservation, and administrator access."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.anomaly_alerts import ADMIN_DENIED_EVENT, ALERT_CATEGORIES, LOCKOUT_EVENT
from app.audit import install_audit_middleware
from app.auth import get_current_user
from app.database import get_db
from app.models.user import AuditLog
from app.routers.admin import router as admin_router


class AnomalyAlertsTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
            execution_options={"schema_translate_map": {"audit": None}},
        )
        self.addCleanup(engine.dispose)
        AuditLog.__table__.create(engine)
        self.sessions = sessionmaker(bind=engine, autoflush=False)
        app = FastAPI()
        install_audit_middleware(app, self.sessions)
        app.include_router(admin_router)

        def audit_database():
            with self.sessions() as db:
                yield db

        def actor(request: Request):
            role = request.headers.get("test-role")
            if role is None:
                raise HTTPException(401)
            request.state.audit_user_id = "test-user"
            return SimpleNamespace(role=role)

        app.dependency_overrides[get_db] = audit_database
        app.dependency_overrides[get_current_user] = actor

        @app.post("/test/login")
        def login(request: Request):
            if request.headers.get("test-lockout"):
                request.state.audit_event_type = LOCKOUT_EVENT
                request.state.audit_user_id = "locked-user"
                request.state.audit_resource_id = "user:locked-user"
                raise HTTPException(423)
            raise HTTPException(401)

        @app.get("/test/server-error")
        def server_error():
            raise HTTPException(503)

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def codes(self):
        with self.sessions() as db:
            return db.scalars(select(AuditLog.error_code).where(AuditLog.category.in_(ALERT_CATEGORIES))).all()

    def test_failed_sign_in_threshold_and_cooldown(self):
        for _ in range(4):
            self.assertEqual(self.client.post("/test/login").status_code, 401)
        self.assertEqual(self.codes(), [])
        with self.assertLogs("app.audit", "WARNING") as logs:
            self.client.post("/test/login")
        self.assertIn("SEC-ALERT-002", logs.output[0])
        self.client.post("/test/login")
        self.assertEqual(self.codes(), ["SEC-ALERT-002"])
        with self.sessions.begin() as db:
            db.execute(update(AuditLog).values(occurred_at=datetime.now(timezone.utc) - timedelta(minutes=11)))
        self.client.post("/test/login")
        self.assertEqual(self.codes(), ["SEC-ALERT-002"])
        for _ in range(4):
            self.client.post("/test/login")
        self.assertEqual(self.codes(), ["SEC-ALERT-002", "SEC-ALERT-002"])

    def test_alerts_are_persisted_and_access_is_admin_only(self):
        self.assertEqual(self.client.post("/test/login", headers={"test-lockout": "1"}).status_code, 423)
        self.assertEqual(self.client.get("/api/admin/alerts").status_code, 401)
        for _ in range(3):
            self.assertEqual(self.client.get("/api/admin/alerts", headers={"test-role": "credit_analyst"}).status_code, 403)
        for _ in range(5):
            self.assertEqual(self.client.get("/test/server-error").status_code, 503)
        response = self.client.get("/api/admin/alerts", headers={"test-role": "admin"})
        self.assertEqual(response.status_code, 200)
        alerts = {record["error_code"]: record for record in response.json()}
        self.assertEqual(set(alerts), {"SEC-ALERT-001", "SEC-ALERT-003", "OPS-ALERT-001"})
        self.assertEqual(alerts["SEC-ALERT-001"]["user_id"], "locked-user")
        self.assertEqual(alerts["OPS-ALERT-001"]["category"], "operational_alert")

    def test_detection_failure_does_not_drop_the_audit_event(self):
        with patch("app.audit.detect_anomalies", side_effect=RuntimeError):
            self.assertEqual(self.client.post("/test/login").status_code, 401)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(AuditLog.event_type)), "login")
