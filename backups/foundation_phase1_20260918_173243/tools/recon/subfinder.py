"""
Subfinder adapter - passive subdomain enumeration.

If the subfinder binary is not installed, this falls back to MockSubfinder
so chains still work during development.
"""
import logging
import shutil
import subprocess
import time
from typing import Any, Dict, List

from tools.base import Tool, ToolResult
from tools.mocks import MockSubfinder

logger = logging.getLogger(__name__)


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
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return ToolResult(success=False, error=str(e),
                              duration_ms=duration, tool_name=self.name)

        subdomains = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"domain": domain, "subdomains": subdomains, "count": len(subdomains)},
            raw=proc.stdout,
            duration_ms=duration,
            tool_name=self.name,
        )