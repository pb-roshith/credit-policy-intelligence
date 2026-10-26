"""Shared response controls for confidential report downloads."""

from __future__ import annotations

import re
from urllib.parse import quote


def safe_export_filename(customer: str, suffix: str, extension: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", customer).strip("._-") or "Credit_Dossier"
    safe_suffix = re.sub(r"[^A-Za-z0-9._-]+", "_", suffix).strip("._-")
    return f"{base}{'_' + safe_suffix if safe_suffix else ''}.{extension}"


def secure_download_headers(filename: str) -> dict[str, str]:
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._") or "report.bin"
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
        ),
        "Cache-Control": "no-store, no-cache, must-revalidate, private, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Content-Type-Options": "nosniff",
        "X-Download-Options": "noopen",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }
