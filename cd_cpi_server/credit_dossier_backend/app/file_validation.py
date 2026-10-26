"""Central allowlist and content-signature validation for uploaded files."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


DOCUMENT_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".csv", ".txt", ".md", ".json"}
)
TEMPLATE_EXTENSIONS = frozenset({".md", ".txt", ".docx", ".doc"})
THEME_EXTENSIONS = frozenset({".pdf", ".txt"})

_OOXML_DIRECTORIES = {
    ".docx": "word/",
    ".xlsx": "xl/",
    ".pptx": "ppt/",
}
_OOXML_ALLOWED_COMPRESSION = frozenset(
    {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
)
_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


class UploadValidationError(ValueError):
    """Raised when an uploaded file is outside the configured allowlist."""


def _safe_filename(filename: str | None) -> str:
    normalized = (filename or "").replace("\\", "/")
    safe = Path(normalized).name.strip()
    if not safe or safe in {".", ".."}:
        raise UploadValidationError("A valid filename with an allowed extension is required.")
    return safe


def _validate_ooxml(file_bytes: bytes, extension: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            entries = archive.infolist()
            if any(
                entry.compress_type not in _OOXML_ALLOWED_COMPRESSION
                for entry in entries
            ):
                return False

            names = [entry.filename for entry in entries]
            return "[Content_Types].xml" in names and any(
                name.startswith(_OOXML_DIRECTORIES[extension]) for name in names
            )
    except (OSError, zipfile.BadZipFile):
        return False


def _looks_like_text(file_bytes: bytes) -> bool:
    if b"\x00" in file_bytes:
        return False
    try:
        file_bytes.decode("utf-8-sig")
        return True
    except UnicodeDecodeError:
        return False


def validate_uploaded_file(
    filename: str | None,
    file_bytes: bytes,
    *,
    allowed_extensions: frozenset[str] = DOCUMENT_EXTENSIONS,
) -> str:
    """Validate extension and content, returning a path-safe filename."""
    safe_filename = _safe_filename(filename)
    extension = Path(safe_filename).suffix.lower()
    supported = ", ".join(sorted(allowed_extensions))
    if extension not in allowed_extensions:
        raise UploadValidationError(
            f"Unsupported file type '{extension or 'none'}'. Allowed types: {supported}."
        )
    if not file_bytes:
        raise UploadValidationError("The uploaded file is empty.")

    valid_content = False
    if extension == ".pdf":
        valid_content = file_bytes.startswith(b"%PDF-")
    elif extension in _OOXML_DIRECTORIES:
        valid_content = _validate_ooxml(file_bytes, extension)
    elif extension in {".doc", ".xls"}:
        valid_content = file_bytes.startswith(_OLE_SIGNATURE)
    elif extension in {".csv", ".txt", ".md", ".json"}:
        valid_content = _looks_like_text(file_bytes)

    if not valid_content:
        raise UploadValidationError(
            f"The file content does not match the '{extension}' extension."
        )
    return safe_filename
