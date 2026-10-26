"""Shared validation policy for JSON request bodies."""

from typing import Any
import re

from pydantic import BaseModel, ConfigDict, model_validator


_ALLOWED_WHITESPACE = {"\t", "\n", "\r"}
_MAX_JSON_DEPTH = 12


def validate_markdown_text(value: str | None) -> str | None:
    """Allow multiline prose/Markdown, but exclude raw HTML and active links."""
    if value is None:
        return value
    _validate_value(value)
    if re.search(r"<\s*(?:/?\s*[A-Za-z]|[!?])", value):
        raise ValueError("Use plain text or Markdown; HTML markup is not supported.")
    if re.search(r"\]\(\s*(?:javascript|vbscript|data)\s*:", value, re.IGNORECASE):
        raise ValueError("Executable or data links are not supported.")
    return value


def _validate_value(value: Any, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("Input nesting is too deep.")
    if isinstance(value, str):
        if any(ord(char) < 32 and char not in _ALLOWED_WHITESPACE for char in value):
            raise ValueError("Input contains a prohibited control character.")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_value(key, depth + 1)
            _validate_value(item, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_value(item, depth + 1)


class StrictInputModel(BaseModel):
    """Reject coercion, unknown fields, and non-text control characters."""

    model_config = ConfigDict(strict=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def validate_raw_input(cls, value: Any) -> Any:
        _validate_value(value)
        return value
