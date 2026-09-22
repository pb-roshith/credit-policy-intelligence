import os
from pathlib import Path
import threading

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

def load_env_file():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env_file()
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ChangeMe!12345")
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
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:root@localhost:5432/credit_policy_intelligence")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_POLICY_MODEL = os.getenv("MISTRAL_POLICY_MODEL", "mistral-medium-latest")
MISTRAL_TIMEOUT_MS = int(os.getenv("MISTRAL_TIMEOUT_MS", "90000"))
MISTRAL_MANUFACTURING_TIMEOUT_MS = int(os.getenv("MISTRAL_MANUFACTURING_TIMEOUT_MS", "450000"))
DATABASE_CONNECT_TIMEOUT_SECONDS = int(os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "10"))
DATABASE_STATEMENT_TIMEOUT_MS = int(os.getenv("DATABASE_STATEMENT_TIMEOUT_MS", "120000"))
DATABASE_TRANSACTION_RETRIES = max(1, int(os.getenv("DATABASE_TRANSACTION_RETRIES", "3")))
DATABASE_RETRY_BASE_DELAY_MS = max(1, int(os.getenv("DATABASE_RETRY_BASE_DELAY_MS", "50")))
POLICY_DOCUMENT_TIMEOUT_SECONDS = int(os.getenv("POLICY_DOCUMENT_TIMEOUT_SECONDS", "1500"))
POLICY_JOB_TIMEOUT_SECONDS = int(os.getenv("POLICY_JOB_TIMEOUT_SECONDS", "36000"))
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

