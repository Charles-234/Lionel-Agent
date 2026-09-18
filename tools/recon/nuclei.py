"""
Nuclei adapter - template-based vulnerability scanning.

Falls back to MockNuclei when the binary is not installed.
"""
import json
import logging
import shutil
import subprocess
import time
from typing import Any, Dict, List

from tools.base import Tool, ToolResult
from tools.mocks import MockNuclei

logger = logging.getLogger(__name__)


class Nuclei(Tool):
    name = "nuclei"
    description = "Template-based vulnerability scan using nuclei"
    category = "recon"
    requires_binary = "nuclei"
    risk_level = "high"
    requires_authorized_target = True
    network_access = True
    supports_simulation = True
    confirmation_required = True
    provenance = "builtin"

    def __init__(self):
        self._mock = MockNuclei()

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "targets": {"type": "array", "items": {"type": "string"}},
                "severity": {"type": "string", "default": "medium,high,critical"},
                "timeout_sec": {"type": "integer", "default": 300},
            },
            "required": ["targets"],
        }

    def available(self) -> bool:
        return shutil.which(self.requires_binary) is not None

    def run(self, targets: List[str], severity: str = "medium,high,critical",
            timeout_sec: int = 300, **kwargs: Any) -> ToolResult:
        if not targets:
            return ToolResult(success=True, data={"findings": [], "count": 0},
                              tool_name=self.name)

        if not self.available():
            return ToolResult(success=False, error="Required tool binary is unavailable.", tool_name=self.name, execution_mode="real", verified=False)

        start = time.time()
        cmd = [
            self.requires_binary, "-jsonl", "-silent", "-no-color",
            "-severity", severity,
        ]
        try:
            proc = subprocess.run(
                cmd, input="\n".join(targets), capture_output=True, text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            duration = int((time.time() - start) * 1000)
            return ToolResult(success=False, error=f"timeout after {timeout_sec}s",
                              duration_ms=duration, tool_name=self.name)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return ToolResult(success=False, error=str(e),
                              duration_ms=duration, tool_name=self.name)

        findings = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                findings.append({
                    "template_id": obj.get("template-id", ""),
                    "name": obj.get("info", {}).get("name", ""),
                    "severity": obj.get("info", {}).get("severity", ""),
                    "target": obj.get("host", ""),
                    "matched_at": obj.get("matched-at", ""),
                })
            except json.JSONDecodeError:
                continue

        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"findings": findings, "count": len(findings)},
            raw=proc.stdout,
            duration_ms=duration,
            tool_name=self.name,
        )