"""Governed filesystem tool - sandboxed read/write within a scoped directory.

PolicyGateway remains the enforcement point. This adapter only keeps its own
input and output clean and enforces a hard sandbox boundary.
"""

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_MAX_READ_BYTES = 1_000_000
_MAX_WRITE_BYTES = 100_000
_MAX_PATH_LENGTH = 512
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SECRET_LINE_RE = re.compile(
    r"(?i)^ *(?:authorization|api[_-]?key|secret|token|password|passwd|bearer)"
    r"[ \t]*[:=].*$"
)

class FileSystemTool(Tool):
    name = "filesystem"
    description = "Read and write files within a sandboxed directory"
    category = "filesystem"
    requires_binary = None
    risk_level = "medium"
    requires_authorized_target = False
    filesystem_access = True
    network_access = False
    supports_simulation = True
    provenance = "builtin"

    def __init__(self, sandbox_dir: Optional[str] = None):
        self.sandbox_dir = Path(sandbox_dir or "").resolve()

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write", "list", "delete"]},
                "path": {"type": "string", "description": "Relative path within sandbox"},
                "content": {"type": "string", "description": "Content to write (for write action)"},
            },
            "required": ["action"],
        }

    def available(self) -> bool:
        return True

    def run(self, action: str, path: str = "", content: str = "", **kwargs: Any) -> ToolResult:
        start = time.time()
        action = (action or "").strip().lower()

        if action not in ("read", "write", "list", "delete"):
            return ToolResult(
                success=False, error=f"Unknown action: {action}. Use read, write, list, or delete.",
                tool_name=self.name, execution_mode="real", verified=False
            )

        if not self.sandbox_dir or not self.sandbox_dir.exists():
            return ToolResult(
                success=False, error="Filesystem sandbox is not configured.",
                tool_name=self.name, execution_mode="real", verified=False
            )

        if action == "list":
            return self._list(path, start)

        if action == "read":
            return self._read(path, start)

        if action == "write":
            return self._write(path, content, start)

        if action == "delete":
            return self._delete(path, start)

        return ToolResult(
            success=False, error="Action handling fell through.",
            tool_name=self.name, execution_mode="real", verified=False
        )

    def _resolve(self, path: str) -> Optional[Path]:
        """Resolve a path within the sandbox. Returns None if outside."""
        if not isinstance(path, str) or not path.strip():
            return None
        raw = path.strip()
        if len(raw) > _MAX_PATH_LENGTH or any(c.isspace() for c in raw):
            return None
        clean = raw.replace("\\", "/").lstrip("/")
        target = (self.sandbox_dir / clean).resolve()
        try:
            if not target.is_relative_to(self.sandbox_dir):
                return None
        except ValueError:
            return None
        return target

    def _read(self, path: str, start: float) -> ToolResult:
        target = self._resolve(path)
        if target is None:
            return ToolResult(
                success=False, error="Invalid or inaccessible path.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        if not target.is_file():
            return ToolResult(
                success=False, error=f"Not a file: {path}",
                tool_name=self.name, execution_mode="real", verified=False
            )
        try:
            raw = target.read_bytes()[:_MAX_READ_BYTES]
        except OSError:
            logger.warning("filesystem read failed for %s", path, exc_info=True)
            return ToolResult(
                success=False, error="Read failed safely without details.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        text = raw.decode("utf-8", errors="replace")
        text = _CONTROL_RE.sub(" ", text)
        lines = []
        for line in text.splitlines():
            if _SECRET_LINE_RE.match(line):
                lines.append("[redacted]")
            else:
                lines.append(line)
        cleaned = "\n".join(lines)
        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"path": path, "content": cleaned, "bytes": len(cleaned), "action": "read"},
            duration_ms=duration, tool_name=self.name, execution_mode="real", verified=False
        )

    def _write(self, path: str, content: str, start: float) -> ToolResult:
        if not isinstance(content, str) or not content.strip():
            return ToolResult(
                success=False, error="Content is required for write action.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        if len(content) > _MAX_WRITE_BYTES:
            return ToolResult(
                success=False, error=f"Content exceeds {_MAX_WRITE_BYTES} byte limit.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        target = self._resolve(path)
        if target is None:
            return ToolResult(
                success=False, error="Invalid or inaccessible path.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError:
            logger.warning("filesystem write failed for %s", path, exc_info=True)
            return ToolResult(
                success=False, error="Write failed safely without details.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"path": path, "bytes": len(content), "action": "write"},
            duration_ms=duration, tool_name=self.name, execution_mode="real", verified=False
        )

    def _list(self, path: str, start: float) -> ToolResult:
        target = self._resolve(path or ".")
        if target is None:
            return ToolResult(
                success=False, error="Invalid or inaccessible path.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        if not target.is_dir():
            return ToolResult(
                success=False, error=f"Not a directory: {path}",
                tool_name=self.name, execution_mode="real", verified=False
            )
        try:
            entries = []
            for p in sorted(target.iterdir()):
                entries.append({
                    "name": p.name,
                    "path": str(p.relative_to(self.sandbox_dir)),
                    "type": "directory" if p.is_dir() else "file",
                    "size": p.stat().st_size if p.is_file() else 0,
                })
        except OSError:
            logger.warning("filesystem list failed for %s", path, exc_info=True)
            return ToolResult(
                success=False, error="List failed safely without details.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"path": path or ".", "entries": entries, "action": "list"},
            duration_ms=duration, tool_name=self.name, execution_mode="real", verified=False
        )

    def _delete(self, path: str, start: float) -> ToolResult:
        target = self._resolve(path)
        if target is None:
            return ToolResult(
                success=False, error="Invalid or inaccessible path.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        if not target.exists():
            return ToolResult(
                success=False, error=f"Path not found: {path}",
                tool_name=self.name, execution_mode="real", verified=False
            )
        try:
            if target.is_dir():
                target.rmdir()
            else:
                target.unlink()
        except OSError:
            logger.warning("filesystem delete failed for %s", path, exc_info=True)
            return ToolResult(
                success=False, error="Delete failed safely without details.",
                tool_name=self.name, execution_mode="real", verified=False
            )
        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"path": path, "action": "delete"},
            duration_ms=duration, tool_name=self.name, execution_mode="real", verified=False
        )
