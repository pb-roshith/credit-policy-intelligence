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
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:root@localhost:5432/credit_policy_intelligence")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_POLICY_MODEL = os.getenv("MISTRAL_POLICY_MODEL", "mistral-medium-latest")
POLICY_OUTPUT_DIR = BASE_DIR / "generated_policies"
POLICY_SOURCE_DIR = BASE_DIR / "policy doc"
POLICY_JOB_LOCK = threading.Lock()
COMPLIANCE_AGENT_LOCK = threading.Lock()
SESSIONS: dict[str, dict] = {}
SECURITY_QUESTIONS = [
    "What was the name of your first school?",
    "What is the name of the city where you were born?",
    "What was the name of your first pet?",
    "What is your mother's maiden name?",
    "What was the make of your first car?",
    "What is the name of your favorite childhood teacher?",
]

