"""
Application configuration using pydantic-settings.
PostgreSQL is the only supported application database.
"""

from pathlib import Path
import os
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.secret_provider import load_runtime_secrets


# Service .env values are the runtime configuration source.
load_runtime_secrets("backend")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Mistral AI ──────────────────────────────────────────────
    AI_PROVIDER: str = "mistral"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    MISTRAL_API_KEY: str = "your_mistral_api_key_here"
    MISTRAL_MODEL: str = "mistral-large-latest"
    MISTRAL_AGENT_MODEL: str = "mistral-large-latest"
    MISTRAL_ACCURACY_JUDGE_ID: str = ""
    MISTRAL_ACCURACY_JUDGE_MAX_SCORE: float = 100.0
    SHARED_DEAL_API_KEY: str = ""
    NEW_DEAL_AGENT_TIMEOUT_MS: int = 90000

    # ── Database ────────────────────────────────────────────────
    # Required in backend/.env or the deployment secret store.
    DATABASE_URL: str
    DB_LOCK_TIMEOUT_SECONDS: int = 5

    # ── Application ─────────────────────────────────────────────
    APP_ENV: str = "development"
    UPLOAD_DIR: str = "./uploads"
    CORS_ALLOWED_ORIGINS: str = (
        "http://localhost:8081|http://localhost:8080|http://localhost:5173|http://localhost:3000|"
        "http://127.0.0.1:8081|http://127.0.0.1:8080|http://127.0.0.1:5173"
    )
    NARRATIVE_EDIT_LOCK_MINUTES: int = 5

    # ── Orchestration ──────────────────────────────────────────
    ORCHESTRATION_ENABLED: bool = True

    # ── Generation ─────────────────────────────────────────────
    MAX_GROUNDING_CHARS: int = 120_000
    GENERATION_SEMAPHORE: int = 3
    ORCHESTRATION_SEMAPHORE: int = 5

    # ── MCP ────────────────────────────────────────────────────
    MANUFACTURE_TIMEOUT_SECONDS: int = 7200
    MCP_CACHE_TTL_SECONDS: int = 300
    MCP_CIRCUIT_BREAKER_SECONDS: int = 60
    MCP_MAX_FAILURES: int = 3
    MCP_SSE_READ_TIMEOUT: float = 300.0  # seconds — max wait for an SSE event

    # ── Production ─────────────────────────────────────────────
    ENABLE_TIMING_METRICS: bool = True
    AZURE_KEY_VAULT_URL: str = ""
    # Trust X-Forwarded-For only when a trusted reverse proxy overwrites it.
    AUDIT_TRUST_X_FORWARDED_FOR: bool = False

    # Persistent report HMAC key configured in the backend .env file.
    REPORT_MASK_SENSITIVE_DATA: bool = True
    REPORT_TOKENIZATION_KEY: str = ""

    # Initial local accounts. Override these values in backend/.env.
    INITIAL_RELATIONSHIP_MANAGER_USER_ID: str = "manager"
    INITIAL_RELATIONSHIP_MANAGER_PASSWORD: str = ""
    INITIAL_CREDIT_ANALYST_USER_ID: str = "analyst"
    INITIAL_CREDIT_ANALYST_PASSWORD: str = ""
    INITIAL_ADMIN_USER_ID: str = "admin"
    INITIAL_ADMIN_PASSWORD: str = ""

    # Absolute session lifetimes. Business roles may not exceed 30 minutes;
    # administrators must use a shorter lifetime of at most 15 minutes.
    SESSION_TIMEOUT_RELATIONSHIP_MANAGER_MINUTES: int = 30
    SESSION_TIMEOUT_CREDIT_ANALYST_MINUTES: int = 30
    SESSION_TIMEOUT_ADMIN_MINUTES: int = 15

    # Authentication policy. SECURITY_QUESTIONS uses | as the separator so it
    # is convenient to override in a .env file.
    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_MAX_LENGTH: int = 31
    PASSWORD_MIN_UPPERCASE: int = 1
    PASSWORD_MIN_LOWERCASE: int = 1
    PASSWORD_MIN_DIGITS: int = 1
    PASSWORD_MIN_SPECIAL: int = 1
    SECURITY_QUESTIONS: str = (
        "What was the name of your first school?|"
        "What city were you born in?|"
        "What was the name of your first pet?|"
        "What is your oldest sibling's middle name?|"
        "What was the make of your first car?|"
        "What is the name of the street where you grew up?"
    )

    @model_validator(mode="after")
    def validate_authentication_configuration(self):
        if not 1 <= self.SESSION_TIMEOUT_RELATIONSHIP_MANAGER_MINUTES <= 30:
            raise ValueError("Relationship Manager sessions must be between 1 and 30 minutes.")
        if not 1 <= self.SESSION_TIMEOUT_CREDIT_ANALYST_MINUTES <= 30:
            raise ValueError("Credit Analyst sessions must be between 1 and 30 minutes.")
        if not 1 <= self.SESSION_TIMEOUT_ADMIN_MINUTES <= 15:
            raise ValueError("Administrator sessions must be between 1 and 15 minutes.")
        if self.SESSION_TIMEOUT_ADMIN_MINUTES >= min(
            self.SESSION_TIMEOUT_RELATIONSHIP_MANAGER_MINUTES,
            self.SESSION_TIMEOUT_CREDIT_ANALYST_MINUTES,
        ):
            raise ValueError("Administrator sessions must be shorter than business-role sessions.")
        if not 1 <= self.PASSWORD_MIN_LENGTH <= self.PASSWORD_MAX_LENGTH <= 1024:
            raise ValueError(
                "Password lengths must satisfy 1 <= minimum <= maximum <= 1024."
            )
        character_counts = (
            self.PASSWORD_MIN_UPPERCASE,
            self.PASSWORD_MIN_LOWERCASE,
            self.PASSWORD_MIN_DIGITS,
            self.PASSWORD_MIN_SPECIAL,
        )
        if any(count < 0 for count in character_counts):
            raise ValueError("Password character requirements cannot be negative.")
        if sum(character_counts) > self.PASSWORD_MAX_LENGTH:
            raise ValueError(
                "Password character requirements cannot exceed the maximum length."
            )
        if len(self.security_question_options) < 3:
            raise ValueError("Configure at least three unique security questions.")
        return self

    @field_validator("DATABASE_URL")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+")):
            raise ValueError("DATABASE_URL must use PostgreSQL.")
        return value

    @property
    def security_question_options(self) -> list[str]:
        return list(dict.fromkeys(
            question.strip()
            for question in self.SECURITY_QUESTIONS.split("|")
            if question.strip()
        ))

    @property
    def upload_path(self) -> Path:
        p = Path(self.UPLOAD_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.CORS_ALLOWED_ORIGINS.split("|") if origin.strip()]

settings = Settings()
settings.AI_PROVIDER = settings.AI_PROVIDER.strip().lower()
if settings.AI_PROVIDER not in {"gemini", "mistral"}:
    raise ValueError("AI_PROVIDER must be mistral or gemini")
os.environ.update(AI_PROVIDER=settings.AI_PROVIDER, GEMINI_API_KEY=settings.GEMINI_API_KEY,
                  GEMINI_MODEL=settings.GEMINI_MODEL)
if settings.AI_PROVIDER == "gemini":
    settings.MISTRAL_API_KEY = settings.GEMINI_API_KEY
    settings.MISTRAL_MODEL = settings.GEMINI_MODEL
    settings.MISTRAL_AGENT_MODEL = settings.GEMINI_MODEL
