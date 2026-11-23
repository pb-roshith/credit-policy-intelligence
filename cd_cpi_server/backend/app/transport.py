"""Transport requirements shared by the API and MCP service."""

import os
import ssl
from urllib.parse import urlsplit


POSTGRES_TLS_OPTIONS = {
    "sslmode": "verify-full",
    "ssl_min_protocol_version": "TLSv1.2",
    "gssencmode": "disable",
}


def is_https_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and "@" not in parsed.netloc


def client_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context(
        cafile=os.getenv("SSL_CERT_FILE") or None,
        capath=os.getenv("SSL_CERT_DIR") or None,
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context
