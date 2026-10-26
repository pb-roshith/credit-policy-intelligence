"""Security primitives for report redaction and environment-backed key management."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from threading import Lock

from app.config import settings


_key_lock = Lock()
_cached_key: bytes | None = None


class KeyManagementError(RuntimeError):
    """Raised when a persistent tokenization key cannot be protected safely."""


def _decode_injected_key(value: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise KeyManagementError("REPORT_TOKENIZATION_KEY must be URL-safe base64.") from exc
    if len(key) < 32:
        raise KeyManagementError("REPORT_TOKENIZATION_KEY must decode to at least 32 bytes.")
    return key


def _load_tokenization_key() -> bytes:
    """Load the persistent report key configured in backend/.env."""
    value = settings.REPORT_TOKENIZATION_KEY.strip()
    if not value:
        raise KeyManagementError("Set REPORT_TOKENIZATION_KEY in backend/.env to URL-safe base64 encoding of at least 32 random bytes.")
    return _decode_injected_key(value)


def tokenization_key() -> bytes:
    global _cached_key
    if _cached_key is None:
        with _key_lock:
            if _cached_key is None:
                _cached_key = _load_tokenization_key()
    return _cached_key


def tokenize_sensitive_value(value: str, namespace: str = "report") -> str:
    """Return a stable, non-reversible HMAC token without exposing the source value."""
    normalized = " ".join(value.strip().casefold().split())
    digest = hmac.new(
        tokenization_key(),
        f"{namespace}\0{normalized}".encode("utf-8"),
        hashlib.sha256,
    ).digest()[:12]
    return "tok_" + base64.b32encode(digest).decode("ascii").rstrip("=").lower()


_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])")),
    ("pan", re.compile(r"(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])", re.IGNORECASE)),
    ("aadhaar", re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")),
    ("account", re.compile(r"(?i)(?P<label>\b(?:account|a/c)\s*(?:number|no\.?|#)?\s*[:=-]?\s*)(?P<value>[A-Z0-9-]{6,34})")),
    ("phone", re.compile(r"(?i)(?P<label>\b(?:phone|mobile|contact)\s*(?:number|no\.?|#)?\s*[:=-]?\s*)(?P<value>\+?[0-9][0-9 ()-]{7,18}[0-9])")),
)


def mask_sensitive_text(text: str) -> str:
    """Replace recognized identifiers with strongly masked, correlatable tokens."""
    if not text or not settings.REPORT_MASK_SENSITIVE_DATA:
        return text
    masked = text
    for namespace, pattern in _SENSITIVE_PATTERNS:
        def replacement(match: re.Match[str], kind: str = namespace) -> str:
            value = match.groupdict().get("value") or match.group(0)
            label = match.groupdict().get("label") or ""
            return f"{label}[MASKED:{tokenize_sensitive_value(value, kind)}]"
        masked = pattern.sub(replacement, masked)
    return masked
