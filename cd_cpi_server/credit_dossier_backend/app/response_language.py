"""Detect unexpected language patterns in English LLM completions."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from app.prompt_canary import record_security_event


MIN_LETTERS = 80
UNEXPECTED_SCRIPT_RATIO = 0.08
MIN_FOREIGN_MARKERS = 4

_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+")
_ENGLISH_MARKERS = frozenset(
    {
        "the", "and", "of", "to", "in", "for", "with", "is", "are", "was",
        "were", "from", "that", "this", "as", "on", "by", "at", "has", "have",
        "company", "financial", "credit", "revenue", "risk", "year", "amount",
    }
)
_FOREIGN_MARKERS = {
    "french": frozenset(
        {"le", "la", "les", "des", "une", "est", "sont", "dans", "pour", "avec", "sur", "que", "qui"}
    ),
    "spanish": frozenset(
        {"el", "la", "los", "las", "una", "es", "son", "del", "para", "con", "por", "que", "como"}
    ),
    "german": frozenset(
        {"der", "die", "das", "den", "dem", "ein", "eine", "ist", "sind", "und", "für", "mit", "von"}
    ),
    "italian": frozenset(
        {"il", "lo", "la", "gli", "una", "del", "della", "è", "sono", "per", "con", "che", "come"}
    ),
    "portuguese": frozenset(
        {"o", "a", "os", "as", "uma", "do", "da", "é", "são", "para", "com", "por", "que", "como"}
    ),
}
_SCRIPT_RANGES = {
    "cyrillic": ((0x0400, 0x052F),),
    "arabic": ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF)),
    "devanagari": ((0x0900, 0x097F),),
    "cjk": ((0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF)),
}


class UnexpectedLanguageDetected(RuntimeError):
    """Raised when a completion unexpectedly changes away from English."""


@dataclass(frozen=True)
class LanguageFinding:
    language_or_script: str
    confidence_signal: str


def _script_for(character: str) -> str | None:
    codepoint = ord(character)
    for name, ranges in _SCRIPT_RANGES.items():
        if any(start <= codepoint <= end for start, end in ranges):
            return name
    return None


def find_unexpected_language(completion: str) -> LanguageFinding | None:
    """Return detection metadata without retaining completion text."""
    letters = [character for character in (completion or "") if character.isalpha()]
    if len(letters) < MIN_LETTERS:
        return None

    script_counts = Counter(
        script
        for character in letters
        if (script := _script_for(character)) is not None
    )
    if script_counts:
        script, count = script_counts.most_common(1)[0]
        ratio = count / len(letters)
        if ratio >= UNEXPECTED_SCRIPT_RATIO:
            return LanguageFinding(script, f"script_ratio={ratio:.3f}")

    words = [word.casefold() for word in _WORD.findall(completion or "")]
    counts = Counter(words)
    english_score = sum(counts[word] for word in _ENGLISH_MARKERS)
    best_language = ""
    best_score = 0
    for language, markers in _FOREIGN_MARKERS.items():
        score = sum(counts[word] for word in markers)
        if score > best_score:
            best_language, best_score = language, score
    if best_score >= MIN_FOREIGN_MARKERS and best_score > english_score:
        return LanguageFinding(
            best_language,
            f"foreign_markers={best_score};english_markers={english_score}",
        )
    return None


def _record_language_event(context: str) -> None:
    record_security_event(
        context,
        event_type="llm_unexpected_language_detected",
        error_code="AI-SEC-003",
        message=(
            "An LLM completion contained an unexpected language pattern. "
            "The completion was blocked before release and requires security review."
        ),
    )


def enforce_expected_language(
    completion: str,
    *,
    context: str,
    recorder: Callable[[str], None] = _record_language_event,
) -> None:
    if find_unexpected_language(completion) is None:
        return
    recorder(context)
    raise UnexpectedLanguageDetected(
        "The generated response was blocked by the language-integrity control."
    )
