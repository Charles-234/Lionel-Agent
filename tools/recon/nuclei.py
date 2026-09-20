"""
Nuclei adapter - template-based vulnerability scanning.

Falls back to MockNuclei when the binary is not installed.
"""
import json
import logging
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List

from tools.base import Tool, ToolResult
from tools.mocks import MockNuclei

logger = logging.getLogger(__name__)

# Check: cap how many targets one call may scan (policy still decides scope).
_MAX_TARGETS = 256
# Check: each target value stays short so oversized input is refused up front.
_MAX_TARGET_LENGTH = 2048
# Sanitize: keep http(s) URLs or bare hostnames; drop flags/whitespace text.
_SAFE_TARGET_RE = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")
_ALLOWED_SEVERITIES = frozenset({"info", "low", "medium", "high", "critical"})
# Verify: only these fields are echoed back from tool output.
_VERIFY_FIELDS = ("template_id", "name", "severity", "target", "matched_at")
_MAX_FINDINGS = 10_000
_MAX_RAW_CHARS = 200_000


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
        if not isinstance(targets, (list, tuple)) or len(targets) > _MAX_TARGETS:
            return ToolResult(success=False, error="Invalid targets supplied.", tool_name=self.name, execution_mode="real", verified=False)
        supplied = [(t or "").strip() for t in targets if isinstance(t, str)]
        if not supplied:
            return ToolResult(success=True, data={"findings": [], "count": 0},
                              tool_name=self.name)
        targets = [_clean_target(t) for t in supplied]
        targets = [t for t in targets if t]
        parts = [(s or "").strip().lower() for s in str(severity or "").split(",")]
        parts = [s for s in parts if s in _ALLOWED_SEVERITIES]
        if not targets:
            return ToolResult(success=False, error="Invalid targets supplied.", tool_name=self.name, execution_mode="real", verified=False)
        if not parts:
            return ToolResult(success=False, error="Invalid severity supplied.", tool_name=self.name, execution_mode="real", verified=False)
        severity = ",".join(parts)
        try:
            timeout_sec = int(timeout_sec)
        except (TypeError, ValueError):
            return ToolResult(success=False, error="Invalid timeout supplied.", tool_name=self.name, execution_mode="real", verified=False)
        timeout_sec = max(1, min(timeout_sec, 600))

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
        except Exception:
            duration = int((time.time() - start) * 1000)
            logger.warning("nuclei execution failed", exc_info=True)
            return ToolResult(success=False, error="Tool execution failed safely without details.",
                              duration_ms=duration, tool_name=self.name)

        findings = []
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
            info = obj.get("info", {})
            info = info if isinstance(info, dict) else {}
            template_id = obj.get("template-id", "")
            template_id = template_id.strip()[:200] if isinstance(template_id, str) else ""
            name = info.get("name", "")
            name = name.strip()[:500] if isinstance(name, str) else ""
            raw_severity = info.get("severity", "")
            raw_severity = raw_severity.strip().lower() if isinstance(raw_severity, str) else ""
            sev = raw_severity if raw_severity in _ALLOWED_SEVERITIES else ""
            target = obj.get("host", "")
            target = target.strip()[:2000] if isinstance(target, str) else ""
            if target and not _looks_like_target(target):
                target = ""
            matched_at = obj.get("matched-at", "")
            matched_at = matched_at.strip()[:2000] if isinstance(matched_at, str) else ""
            if matched_at and not _looks_like_target(matched_at):
                matched_at = ""
            findings.append({
                "template_id": template_id,
                "name": name,
                "severity": sev,
                "target": target,
                "matched_at": matched_at,
            })
            if len(findings) >= _MAX_FINDINGS:
                break

        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"findings": findings, "count": len(findings)},
            # Verify: echo structured fields only, never raw tool text.
            raw=json.dumps(
                [{k: entry[k] for k in _VERIFY_FIELDS} for entry in findings]
            )[:_MAX_RAW_CHARS],
            duration_ms=duration,
            tool_name=self.name,
        )


def _clean_target(value: str) -> str:
    """Sanitize one target value; return "" when it is not a safe target."""
    text = (value or "").strip()
    if not text or len(text) > _MAX_TARGET_LENGTH:
        return ""
    if text.startswith("-") or any(c.isspace() for c in text):
        return ""
    if _looks_like_target(text):
        return text
    return ""


def _looks_like_target(value: str) -> bool:
    text = value.strip().lower()
    if text.startswith("http://") or text.startswith("https://"):
        rest = text.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
        return bool(_SAFE_TARGET_RE.fullmatch(rest))
    host = text.split("/", 1)[0].split(":", 1)[0]
    return bool(_SAFE_TARGET_RE.fullmatch(host))