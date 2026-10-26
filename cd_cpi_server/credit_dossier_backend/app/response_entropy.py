"""Detect suspicious high-entropy or encoded segments in LLM completions."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from app.prompt_canary import record_security_event


MIN_CANDIDATE_LENGTH = 48
ENTROPY_THRESHOLD = 4.3
HEX_ENTROPY_THRESHOLD = 3.5
_ENCODED_CANDIDATE = re.compile(
    rf"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/=_-]{{{MIN_CANDIDATE_LENGTH},}}(?![A-Za-z0-9+/=_-])"
)
_HEX_CANDIDATE = re.compile(
    rf"(?<![0-9A-Fa-f])[0-9A-Fa-f]{{{MIN_CANDIDATE_LENGTH},}}(?![0-9A-Fa-f])"
)


class HighEntropyResponseDetected(RuntimeError):
    """Raised when a completion contains suspicious encoded/random material."""


@dataclass(frozen=True)
class EntropyFinding:
    kind: str
    length: int
    entropy: float


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def find_high_entropy_segments(completion: str) -> list[EntropyFinding]:
    """Return metadata only; suspicious content is never copied into findings/logs."""
    findings: list[EntropyFinding] = []
    seen_spans: set[tuple[int, int]] = set()
    for kind, pattern, threshold in (
        ("hex", _HEX_CANDIDATE, HEX_ENTROPY_THRESHOLD),
        ("encoded", _ENCODED_CANDIDATE, ENTROPY_THRESHOLD),
    ):
        for match in pattern.finditer(completion or ""):
            span = match.span()
            if span in seen_spans:
                continue
            candidate = match.group(0)
            entropy = shannon_entropy(candidate)
            if entropy >= threshold:
                findings.append(
                    EntropyFinding(
                        kind=kind,
                        length=len(candidate),
                        entropy=round(entropy, 3),
                    )
                )
                seen_spans.add(span)
    return findings


def _record_entropy_event(context: str) -> None:
    record_security_event(
        context,
        event_type="llm_high_entropy_detected",
        error_code="AI-SEC-002",
        message=(
            "An LLM completion contained a suspicious high-entropy or encoded segment. "
            "The completion was blocked before release and requires security review."
        ),
    )


def enforce_response_entropy(
    completion: str,
    *,
    context: str,
    recorder: Callable[[str], None] = _record_entropy_event,
) -> None:
    findings = find_high_entropy_segments(completion)
    if not findings:
        return
    recorder(context)
    raise HighEntropyResponseDetected(
        "The generated response was blocked by the encoded-content security control."
    )
