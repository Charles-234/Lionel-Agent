"""
Subfinder adapter - passive subdomain enumeration.

If the subfinder binary is not installed, this falls back to MockSubfinder
so chains still work during development.
"""
import logging
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List

from tools.base import Tool, ToolResult
from tools.mocks import MockSubfinder

logger = logging.getLogger(__name__)

# Check: letters, digits, dots, hyphens only; each label 1-63 chars,
# no leading/trailing hyphen per label, at least one dot, TLD letters only.
_DOMAIN_RE = re.compile(
    r"(?=.{1,255}\Z)(?:(?!-)[a-z0-9-]{1,63}(?<!-)\.)+(?!-)[a-z]{2,63}(?<!-)\Z"
)
# Sanitize: same shape enforced per line of tool output.
_HOST_RE = re.compile(
    r"(?=.{1,255}\Z)(?:(?!-)[a-z0-9-]{1,63}(?<!-)\.)+(?!-)[a-z]{2,63}(?<!-)\Z"
)
_MAX_SUBDOMAINS = 10_000
_MAX_RAW_CHARS = 200_000


class Subfinder(Tool):
    name = "subfinder"
    description = "Passively enumerate subdomains for a domain using subfinder"
    category = "recon"
    requires_binary = "subfinder"
    risk_level = "medium"
    requires_authorized_target = True
    network_access = True
    supports_simulation = True
    provenance = "builtin"

    def __init__(self):
        self._mock = MockSubfinder()

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain"},
                "silent": {"type": "boolean", "default": True},
                "timeout_sec": {"type": "integer", "default": 120},
            },
            "required": ["domain"],
        }

    def available(self) -> bool:
        return shutil.which(self.requires_binary) is not None

    def run(self, domain: str, silent: bool = True, timeout_sec: int = 120, **kwargs: Any) -> ToolResult:
        domain = (domain or "").strip().lower()
        if not domain or len(domain) > 255 or not _DOMAIN_RE.fullmatch(domain):
            return ToolResult(success=False, error="Invalid domain supplied.", tool_name=self.name, execution_mode="real", verified=False)
        try:
            timeout_sec = int(timeout_sec)
        except (TypeError, ValueError):
            return ToolResult(success=False, error="Invalid timeout supplied.", tool_name=self.name, execution_mode="real", verified=False)
        timeout_sec = max(1, min(timeout_sec, 600))
        if not self.available():
            return ToolResult(success=False, error="Required tool binary is unavailable.", tool_name=self.name, execution_mode="real", verified=False)

        start = time.time()
        cmd = [self.requires_binary, "-d", domain, "-silent"]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            duration = int((time.time() - start) * 1000)
            return ToolResult(success=False, error=f"timeout after {timeout_sec}s",
                              duration_ms=duration, tool_name=self.name)
        except Exception:
            duration = int((time.time() - start) * 1000)
            logger.warning("subfinder execution failed", exc_info=True)
            return ToolResult(success=False, error="Tool execution failed safely without details.",
                              duration_ms=duration, tool_name=self.name)

        subdomains: List[str] = []
        for line in proc.stdout.splitlines():
            candidate = line.strip().lower()
            if not candidate or len(candidate) > 255:
                continue
            if not _HOST_RE.fullmatch(candidate):
                continue
            subdomains.append(candidate)
            if len(subdomains) >= _MAX_SUBDOMAINS:
                break
        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            # Verify: echo only the validated domain plus validated hostnames
            # actually seen, one per line.  Never return free-form tool text.
            data={"domain": domain, "subdomains": subdomains, "count": len(subdomains)},
            raw="\n".join(subdomains)[:_MAX_RAW_CHARS],
            duration_ms=duration,
            tool_name=self.name,
        )