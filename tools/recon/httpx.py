"""
HTTPX adapter - HTTP probing at scale.

Falls back to MockHttpx when the binary is not installed.
"""
import json
import logging
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List

from tools.base import Tool, ToolResult
from tools.mocks import MockHttpx

logger = logging.getLogger(__name__)

# Check: cap how many hosts one call may probe (policy still decides scope).
_MAX_HOSTS = 256
# Check: each host value stays short so oversized input is refused up front.
_MAX_HOST_LENGTH = 255
# Sanitize: only http(s) URLs or bare hostnames are kept; anything else
# (shell flags, whitespace, control text) is dropped before the binary runs.
_SAFE_HOST_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")
# Verify: only these fields are echoed back from tool output.
_VERIFY_FIELDS = ("url", "status_code", "title", "tech", "port")
_MAX_LIVE = 10_000
_MAX_RAW_CHARS = 200_000


class Httpx(Tool):
    name = "httpx"
    description = "Probe HTTP services on a list of hosts using httpx"
    category = "recon"
    requires_binary = "httpx"
    risk_level = "medium"
    requires_authorized_target = True
    network_access = True
    supports_simulation = True
    provenance = "builtin"

    def __init__(self):
        self._mock = MockHttpx()

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "hosts": {"type": "array", "items": {"type": "string"}},
                "timeout_sec": {"type": "integer", "default": 120},
            },
            "required": ["hosts"],
        }

    def available(self) -> bool:
        return shutil.which(self.requires_binary) is not None

    def run(self, hosts: List[str], timeout_sec: int = 120, **kwargs: Any) -> ToolResult:
        if not isinstance(hosts, (list, tuple)) or len(hosts) > _MAX_HOSTS:
            return ToolResult(success=False, error="Invalid hosts supplied.", tool_name=self.name, execution_mode="real", verified=False)
        cleaned = [(h or "").strip() for h in hosts if isinstance(h, str)]
        if not cleaned:
            return ToolResult(success=True, data={"live_hosts": [], "count": 0},
                              tool_name=self.name)
        hosts = [_clean_host(h) for h in cleaned]
        hosts = [h for h in hosts if h]
        if not hosts:
            return ToolResult(success=False, error="Invalid hosts supplied.", tool_name=self.name, execution_mode="real", verified=False)
        try:
            timeout_sec = int(timeout_sec)
        except (TypeError, ValueError):
            return ToolResult(success=False, error="Invalid timeout supplied.", tool_name=self.name, execution_mode="real", verified=False)
        timeout_sec = max(1, min(timeout_sec, 600))

        if not self.available():
            return ToolResult(success=False, error="Required tool binary is unavailable.", tool_name=self.name, execution_mode="real", verified=False)

        start = time.time()
        cmd = [self.requires_binary, "-json", "-silent", "-no-color"]
        try:
            proc = subprocess.run(
                cmd, input="\n".join(hosts), capture_output=True, text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            duration = int((time.time() - start) * 1000)
            return ToolResult(success=False, error=f"timeout after {timeout_sec}s",
                              duration_ms=duration, tool_name=self.name)
        except Exception:
            duration = int((time.time() - start) * 1000)
            logger.warning("httpx execution failed", exc_info=True)
            return ToolResult(success=False, error="Tool execution failed safely without details.",
                              duration_ms=duration, tool_name=self.name)

        live = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line or len(line) > 10_000:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            # Verify: keep only known scalar fields; drop nested/tool text.
            url = obj.get("url", "")
            url = url if isinstance(url, str) else ""
            url = url.strip()[:2000]
            if url and not _looks_like_url_or_host(url):
                url = ""
            try:
                status_code = int(obj.get("status_code", 0))
            except (TypeError, ValueError):
                status_code = 0
            status_code = max(0, min(status_code, 599))
            title = obj.get("title", "")
            title = title.strip()[:500] if isinstance(title, str) else ""
            tech = obj.get("tech", [])
            tech = [str(t)[:100] for t in tech if isinstance(t, str)][:20] if isinstance(tech, list) else []
            try:
                port = int(obj.get("port", 0))
            except (TypeError, ValueError):
                port = 0
            port = max(0, min(port, 65535))
            live.append({
                "url": url,
                "status_code": status_code,
                "title": title,
                "tech": tech,
                "port": port,
            })
            if len(live) >= _MAX_LIVE:
                break

        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"live_hosts": live, "count": len(live)},
            # Verify: echo structured fields only, never raw tool text.
            raw=json.dumps(
                [{k: entry[k] for k in _VERIFY_FIELDS} for entry in live]
            )[:_MAX_RAW_CHARS],
            duration_ms=duration,
            tool_name=self.name,
        )


def _clean_host(value: str) -> str:
    """Sanitize one host value; return "" when it is not a safe host/URL."""
    text = (value or "").strip()
    if not text or len(text) > _MAX_HOST_LENGTH:
        return ""
    if text.startswith("-") or any(c.isspace() for c in text):
        return ""
    lowered = text.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        rest = lowered.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
        if _SAFE_HOST_RE.fullmatch(rest):
            return text
        return ""
    if _SAFE_HOST_RE.fullmatch(lowered):
        return text
    return ""


def _looks_like_url_or_host(value: str) -> bool:
    text = value.strip().lower()
    if text.startswith("http://") or text.startswith("https://"):
        rest = text.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
        return bool(_SAFE_HOST_RE.fullmatch(rest))
    host = text.split("/", 1)[0].split(":", 1)[0]
    return bool(_SAFE_HOST_RE.fullmatch(host))