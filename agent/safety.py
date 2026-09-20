"""Input safety screen: check, clean, and prove a request is safe to handle.

This screen sits before planning only. It checks shape, removes unsafe
characters for display, and proves results against outside facts. It never
authorizes, plans, selects tools, sets permissions, executes, or audits.
Every later safety check still runs unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


EMPTY_MESSAGE = "Request text is required."
TOO_LONG_MESSAGE = "Request text is too long to handle safely."
BAD_TYPE_MESSAGE = "Request text must be words, not another data type."

MAX_REQUEST_CHARS = 10_000
MAX_DISPLAY_CHARS = 1_000

_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}"),
]
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SafetyError(ValueError):
    """A plain, safe error an outside screen can show as-is."""


@dataclass(frozen=True)
class CheckedRequest:
    """A request that passed the shape check. Grants nothing."""

    cleaned_text: str


@dataclass(frozen=True)
class Verification:
    """A proof label for a finished step. Never upgrades a guess."""

    status: str  # "VERIFIED" or "UNVERIFIED"
    note: str


def check_request(raw_text: Any) -> CheckedRequest:
    """Check the shape of one request. Refuse empties and oversized input."""
    if not isinstance(raw_text, str):
        raise SafetyError(BAD_TYPE_MESSAGE)
    cleaned = " ".join(raw_text.split())
    if not cleaned:
        raise SafetyError(EMPTY_MESSAGE)
    if len(raw_text) > MAX_REQUEST_CHARS:
        raise SafetyError(TOO_LONG_MESSAGE)
    return CheckedRequest(cleaned_text=cleaned)


def sanitize_for_display(value: Any) -> str:
    """Clean one value so it is safe to show on an outside screen."""
    text = "" if value is None else str(value)
    text = _CONTROL_CHARS.sub("", text)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    text = " ".join(text.split())
    if len(text) > MAX_DISPLAY_CHARS:
        text = text[:MAX_DISPLAY_CHARS] + "..."
    return text


def verification_status(*, success: bool, evidence_present: bool,
                        execution_mode: Optional[str] = None) -> Verification:
    """Label a finished step. Simulation output is never marked verified."""
    if execution_mode == "simulation":
        return Verification(status="UNVERIFIED",
                            note="Simulation output is never treated as proven.")
    if success and evidence_present:
        return Verification(status="VERIFIED",
                            note="Outside evidence supports the result.")
    return Verification(status="UNVERIFIED",
                        note="No supporting evidence was supplied.")