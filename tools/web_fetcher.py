"""
Governed web fetcher - safe public text retrieval.

This tool reads public web pages as text. It is deliberately narrow:

- Only http(s) URLs are accepted; every other scheme is refused.
- The response body is never executed, never rendered, and never followed
  as HTML beyond simple tag stripping.
- Text is size-capped, control-character-cleaned, and stripped of content
  that looks like embedded secrets before it ever leaves the tool.
- Private-address ranges are refused so the tool cannot be pointed at
  internal infrastructure.

PolicyGateway remains the single enforcement point; this adapter only
keeps its own input and output clean.
"""
import logging
import re
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

from tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_MAX_URL_LENGTH = 2048
_MAX_BODY_BYTES = 1_000_000
_MAX_TEXT_CHARS = 200_000
_REQUEST_TIMEOUT = 30
_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"169\.254\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|\[::1\])$",
    re.IGNORECASE,
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SCRIPT_RE = re.compile(r"<(?:(script|style)\b[^>]*>.*?</\1\s*>)", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
# Verify: drop obvious credential material from stored text.
_SECRET_LINE_RE = re.compile(
    r"(?i)^ *(?:authorization|api[_-]?key|secret|token|password|passwd|bearer)"
    r"[ \t]*[:=].*$"
)


class WebFetcher(Tool):
    name = "web_fetch"
    description = "Fetch public web page text safely for research"
    category = "research"
    requires_binary = None
    risk_level = "medium"
    requires_authorized_target = False
    network_access = True
    supports_simulation = True
    provenance = "builtin"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public http(s) URL"},
                "timeout_sec": {"type": "integer", "default": 30},
            },
            "required": ["url"],
        }

    def available(self) -> bool:
        return True

    def run(self, url: str, timeout_sec: int = 30, **kwargs: Any) -> ToolResult:
        cleaned_url = _clean_url(url)
        if not cleaned_url:
            return ToolResult(
                success=False,
                error="Only public http(s) URLs are supported.",
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )
        try:
            timeout_sec = int(timeout_sec)
        except (TypeError, ValueError):
            return ToolResult(success=False, error="Invalid timeout supplied.",
                              tool_name=self.name, execution_mode="real", verified=False)
        timeout_sec = max(1, min(timeout_sec, 60))

        start = time.time()
        try:
            resp = requests.get(
                cleaned_url,
                timeout=timeout_sec,
                stream=True,
                headers={"User-Agent": "LionelGovernedFetcher/1.0"},
            )
        except requests.exceptions.RequestException:
            duration = int((time.time() - start) * 1000)
            logger.warning("web_fetch request failed", exc_info=True)
            return ToolResult(
                success=False,
                error="Fetch failed safely without details.",
                duration_ms=duration,
                tool_name=self.name,
            )

        duration = int((time.time() - start) * 1000)
        if resp.status_code != 200:
            return ToolResult(
                success=False,
                error=f"Fetch was refused with status {resp.status_code}.",
                duration_ms=duration,
                tool_name=self.name,
            )

        body = b""
        for chunk in resp.iter_content(chunk_size=65536):
            body += chunk
            if len(body) >= _MAX_BODY_BYTES:
                break
        resp.close()

        text = _extract_text(body)
        if not text:
            return ToolResult(
                success=True,
                data={"url": cleaned_url, "text": "", "chars": 0},
                duration_ms=duration,
                tool_name=self.name,
            )
        return ToolResult(
            success=True,
            data={"url": cleaned_url, "text": text, "chars": len(text)},
            duration_ms=duration,
            tool_name=self.name,
        )


def _clean_url(value: Any) -> str:
    """Sanitize one URL; return \"\" when it is not a safe public http(s) URL."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or len(text) > _MAX_URL_LENGTH or any(c.isspace() for c in text):
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""
    if _PRIVATE_HOST_RE.match(parsed.hostname):
        return ""
    return text


def _extract_text(body: bytes) -> str:
    """Check, sanitize, and cap raw response bytes into clean text."""
    text = body[:_MAX_BODY_BYTES].decode("utf-8", errors="replace")
    text = _SCRIPT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = _CONTROL_RE.sub(" ", text)
    lines = []
    for line in text.splitlines():
        if _SECRET_LINE_RE.match(line):
            lines.append("[redacted]")
        else:
            lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned[:_MAX_TEXT_CHARS]