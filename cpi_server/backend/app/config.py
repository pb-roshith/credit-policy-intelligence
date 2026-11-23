import os
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict

BORROWER_PREFIXES = ["Apex", "Beacon", "Crescent", "Evergreen", "Frontier", "Granite", "Horizon", "Meridian", "Northstar", "Summit"]
BORROWER_SUFFIXES = ["Industries", "Holdings", "Logistics", "Energy", "Foods", "Systems", "Aviation", "Chemicals", "Technologies", "Infrastructure"]
INDUSTRY_FACILITIES = [
    ("Manufacturing", "Term Loan"), ("Commercial RE", "Construction"),
    ("Transportation", "Revolver"), ("Energy", "Project Finance"),
    ("Healthcare", "Term Loan"), ("Consumer", "Revolver"),
    ("Technology", "Bridge"), ("Aviation", "Aircraft Finance"),
    ("Chemicals", "Term Loan"), ("Mining", "Reserve Based"),
]
RATINGS = ["A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+"]
GEOGRAPHIES = [
    "US Northeast", "US Southeast", "US Midwest", "US West", "Canada",
    "United Kingdom", "Europe", "Middle East & Africa", "Asia Pacific",
    "Latin America",
]
GEOGRAPHY_RISK = {
    "US Northeast": "Low", "US Southeast": "Low", "US Midwest": "Low",
    "US West": "Low", "Canada": "Low", "United Kingdom": "Low",
    "Europe": "Medium", "Asia Pacific": "Medium",
    "Middle East & Africa": "High", "Latin America": "High",
}
REQUEST_STATUSES = ["In Review", "Escalated", "Approved", "Pending", "Declined"]
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_NAMES = {
    "ADMIN_PASSWORD", "DATABASE_URL", "MISTRAL_API_KEY", "GEMINI_API_KEY",
    "SHARED_DEAL_API_KEY", "DATA_ENCRYPTION_KEY", "DATA_ENCRYPTION_PREVIOUS_KEYS",
}

def load_env_file():
    local_secrets = {}
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return local_secrets
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.removesuffix("_FILE") in SECRET_NAMES:
            local_secrets.setdefault(key, value)
        else:
            os.environ.setdefault(key, value)
    return local_secrets

_local_secrets = load_env_file()
APP_ENV = os.getenv("APP_ENV", "production").strip().lower()
_development = APP_ENV == "development"


def read_deployment_secret(name: str, default: str = "") -> str:
    local = _local_secrets if _development else {}
    key = os.getenv(name, local.get(name, default if _development else ""))
    file_setting = f"{name}_FILE"
    path_value = os.getenv(file_setting, local.get(file_setting, ""))
    if not path_value:
        return key
    if os.getenv(name, local.get(name, "")):
        raise RuntimeError(f"Configure only one secret source for {name}")
    try:
        path = Path(path_value).resolve(strict=True)
        if not path.is_file() or (not _development and path.is_relative_to(BASE_DIR.parent)):
            raise ValueError("Invalid secret location")
        with path.open(encoding="utf-8") as secret:
            value = secret.read(16_385)
        if len(value) > 16_384 or not value.strip():
            raise ValueError("Invalid secret contents")
        return value.rstrip("\r\n")
    except (OSError, ValueError):
        raise RuntimeError(f"Could not read the mounted secret for {name}") from None


def positive_timeout(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "admin")
ADMIN_PASSWORD = read_deployment_secret("ADMIN_PASSWORD")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
ENABLE_HSTS = os.getenv("ENABLE_HSTS", "false").strip().lower() in {"1", "true", "yes", "on"}
MAX_REQUEST_BODY_BYTES = max(1024, int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576")))
RATE_LIMIT_REQUESTS = max(1, int(os.getenv("RATE_LIMIT_REQUESTS", "120")))
RATE_LIMIT_WINDOW_SECONDS = max(1, int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
DATABASE_URL = read_deployment_secret("DATABASE_URL", "postgresql://postgres:root@localhost:5432/credit_policy_intelligence")
MISTRAL_API_KEY = read_deployment_secret("MISTRAL_API_KEY")
MISTRAL_POLICY_MODEL = os.getenv("MISTRAL_POLICY_MODEL", "mistral-medium-latest")
AI_PROVIDER = os.getenv("AI_PROVIDER", "mistral").strip().lower()
GEMINI_API_KEY = read_deployment_secret("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
if AI_PROVIDER not in {"mistral", "gemini"}:
    raise ValueError("AI_PROVIDER must be mistral or gemini")
# Existing call sites use these aliases for the active provider.
if AI_PROVIDER == "gemini":
    MISTRAL_API_KEY = GEMINI_API_KEY
    MISTRAL_POLICY_MODEL = GEMINI_MODEL
MISTRAL_TIMEOUT_MS = positive_timeout("MISTRAL_TIMEOUT_MS", 90_000)
SHARED_DEAL_API_URL = os.getenv("SHARED_DEAL_API_URL", "http://127.0.0.1:8003").rstrip("/")
SHARED_DEAL_API_KEY = read_deployment_secret("SHARED_DEAL_API_KEY")
SHARED_DEAL_TIMEOUT_SECONDS = positive_timeout("SHARED_DEAL_TIMEOUT_SECONDS", 120)
MISTRAL_MANUFACTURING_TIMEOUT_MS = positive_timeout("MISTRAL_MANUFACTURING_TIMEOUT_MS", 450_000)
DATABASE_CONNECT_TIMEOUT_SECONDS = positive_timeout("DATABASE_CONNECT_TIMEOUT_SECONDS", 10)
DATABASE_STATEMENT_TIMEOUT_MS = positive_timeout("DATABASE_STATEMENT_TIMEOUT_MS", 120_000)
DATABASE_TRANSACTION_RETRIES = max(1, int(os.getenv("DATABASE_TRANSACTION_RETRIES", "3")))
DATABASE_RETRY_BASE_DELAY_MS = max(1, int(os.getenv("DATABASE_RETRY_BASE_DELAY_MS", "50")))
POLICY_DOCUMENT_TIMEOUT_SECONDS = positive_timeout("POLICY_DOCUMENT_TIMEOUT_SECONDS", 1_500)
POLICY_JOB_TIMEOUT_SECONDS = positive_timeout("POLICY_JOB_TIMEOUT_SECONDS", 36_000)
POLICY_OUTPUT_DIR = BASE_DIR / "generated_policies"
POLICY_SOURCE_DIR = BASE_DIR / "policy doc"
POLICY_JOB_LOCK = threading.Lock()
COMPLIANCE_AGENT_LOCK = threading.Lock()
SECURITY_QUESTIONS = [
    "What was the name of your first school?",
    "What is the name of the city where you were born?",
    "What was the name of your first pet?",
    "What is your mother's maiden name?",
    "What was the make of your first car?",
    "What is the name of your favorite childhood teacher?",
]


# Governed inventory: AI never activates operational rules.
RULE_MAX_FILE_BYTES = int(os.getenv("RULE_MAX_FILE_BYTES", "20971520"))
RULE_EXTRACTION_RETRIES = max(1, min(3, int(os.getenv("RULE_EXTRACTION_RETRIES", "2"))))
RULE_CLAUSE_BATCH_SIZE = max(1, min(10, int(os.getenv("RULE_CLAUSE_BATCH_SIZE", "4"))))
def validate_encryption_key(key: str) -> str:
    if key:
        try:
            if len(key) != 44:
                raise ValueError("Invalid Fernet key length")
            Fernet(key)
        except ValueError:
            raise RuntimeError("The encryption secret must be a valid 32-byte Fernet key") from None
    return key


DATA_ENCRYPTION_KEY = validate_encryption_key(read_deployment_secret("DATA_ENCRYPTION_KEY"))
DATA_ENCRYPTION_PREVIOUS_KEYS = tuple(
    validate_encryption_key(key.strip())
    for key in read_deployment_secret("DATA_ENCRYPTION_PREVIOUS_KEYS").split(",")
    if key.strip()
)
RULE_DEMO_AUTO_APPROVE = APP_ENV == "development" and os.getenv("RULE_DEMO_AUTO_APPROVE", "false").lower() == "true"


def _is_privileged_os_user() -> bool:
    if os.name == "nt":
        from ctypes import windll

        return bool(windll.shell32.IsUserAnAdmin())
    return os.geteuid() == 0


def validate_operational_config():
    if APP_ENV == "development":
        return

    errors = []
    if sys.flags.optimize:
        errors.append("Run the production backend without Python optimization flags")
    if _is_privileged_os_user():
        errors.append("Run the production service under a non-administrative OS identity")
    if not DATA_ENCRYPTION_KEY:
        errors.append("Supply a deployment encryption secret using DATA_ENCRYPTION_KEY or DATA_ENCRYPTION_KEY_FILE")
    if len(ADMIN_PASSWORD) < 12 or ADMIN_PASSWORD in {"ChangeMe!12345", "replace-with-a-strong-admin-password"}:
        errors.append("ADMIN_PASSWORD must be a non-default credential of at least 12 characters")
    if not SESSION_COOKIE_SECURE or not ENABLE_HSTS:
        errors.append("SESSION_COOKIE_SECURE and ENABLE_HSTS must both be enabled")
    if not CORS_ORIGINS or any(
        not origin.startswith("https://") or "*" in origin for origin in CORS_ORIGINS
    ):
        errors.append("CORS_ORIGINS must contain exact HTTPS origins")
    if not SHARED_DEAL_API_KEY or SHARED_DEAL_API_KEY == "replace-with-a-random-service-key":
        errors.append("SHARED_DEAL_API_KEY must contain the configured service secret")
    shared_url = urlsplit(SHARED_DEAL_API_URL)
    if shared_url.scheme != "https" and not (
        shared_url.scheme == "http" and shared_url.hostname in {"127.0.0.1", "::1", "localhost"}
    ):
        errors.append("SHARED_DEAL_API_URL must use HTTPS or loopback HTTP")
    try:
        db_options = conninfo_to_dict(DATABASE_URL)
    except ProgrammingError:
        errors.append("DATABASE_URL is not a valid PostgreSQL connection string")
    else:
        if (db_options.get("sslmode") != "verify-full"
                or db_options.get("ssl_min_protocol_version") not in {"TLSv1.2", "TLSv1.3"}
                or db_options.get("ssl_max_protocol_version") not in {None, "TLSv1.2", "TLSv1.3"}
                or db_options.get("gssencmode") != "disable"):
            errors.append("DATABASE_URL must require verified TLS 1.2 or newer and set gssencmode=disable")
    if errors:
        raise RuntimeError("Unsafe CPI deployment configuration. " + ". ".join(errors))

RULE_INVENTORY_WORKERS = max(1, min(4, int(os.getenv("RULE_INVENTORY_WORKERS", "2"))))
POLICY_GRAPH_LLM_FALLBACK = os.getenv('POLICY_GRAPH_LLM_FALLBACK', 'false').lower() == 'true'
POLICY_GRAPH_FALLBACK_MAX_SPANS = max(0,min(100,int(os.getenv('POLICY_GRAPH_FALLBACK_MAX_SPANS','20'))))
