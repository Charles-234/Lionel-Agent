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
MAX_DISPLAY_CHARS = 20_000

_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}"),
]
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HIDDEN_REASONING_BLOCK = re.compile(
    r"(?is)<(?:think|analysis|reasoning)>.*?</(?:think|analysis|reasoning)>"
)
_LABELED_REASONING = re.compile(
    r"(?is)^\s*(?:thinking|analysis|reasoning|internal thoughts?)\s*:.*?"
    r"(?:\n\s*(?:final answer|answer)\s*:)(?:\s*)"
)


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
    """Clean one value so it is safe to show on an outside screen.

    Long replies are still allowed to flow through Telegram in chunks; this
    function preserves structured Markdown and newline boundaries instead of
    flattening everything into a single paragraph.
    """
    text = "" if value is None else str(value)
    text = _HIDDEN_REASONING_BLOCK.sub("", text)
    text = _LABELED_REASONING.sub("", text)
    text = _CONTROL_CHARS.sub("", text)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)

    # Preserve document structure for Markdown/code blocks while collapsing
    # accidental whitespace noise.  We keep line breaks since Telegram replies
    # are chunked later and markdown fences are a valid part of the payload.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(" ".join(line.split()) for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) > MAX_DISPLAY_CHARS:
        text = text[:MAX_DISPLAY_CHARS].rstrip()
        if text and not text.endswith("\n"):
            text += "\n"
        text += "..."
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