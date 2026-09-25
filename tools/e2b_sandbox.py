"""Governed E2B code execution sandbox.

Runs code in an isolated E2B sandbox. The E2B API key must be set via
E2B_API_KEY in .env. Without the key or the SDK, the tool returns a clean refusal.
"""

import logging
import time
from typing import Any, Dict, Optional

from tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_MAX_CODE_LENGTH = 50_000
SUPPORTED_LANGUAGES = ("python", "javascript", "go", "cpp", "java", "rust")


class E2BSandboxTool(Tool):
    name = "e2b_sandbox"
    description = "Execute code in an isolated E2B sandbox"
    category = "code_execution"
    requires_binary = None
    risk_level = "high"
    requires_authorized_target = False
    network_access = False
    filesystem_access = False
    credentials_required = True
    supports_simulation = False
    confirmation_required = True
    provenance = "builtin"

    def __init__(self):
        pass

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Source code to execute"},
                "language": {
                    "type": "string",
                    "enum": list(SUPPORTED_LANGUAGES),
                    "default": "python",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (1-300)",
                },
                "files": {
                    "type": "object",
                    "description": "Optional files to inject into the sandbox",
                },
            },
            "required": ["code", "language"],
        }

    def available(self) -> bool:
        try:
            import config
            return bool(config.E2B_API_KEY)
        except Exception:
            return False

    def run(
        self,
        code: str,
        language: str = "python",
        timeout: int = 60,
        files: Optional[Dict] = None,
        **kwargs: Any,
    ) -> ToolResult:
        start = time.time()

        if not isinstance(code, str) or not code.strip():
            return ToolResult(
                success=False,
                error="Code is required.",
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )

        if len(code) > _MAX_CODE_LENGTH:
            return ToolResult(
                success=False,
                error=f"Code exceeds {_MAX_CODE_LENGTH} character limit.",
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )

        lang = (language or "python").lower()
        if lang not in SUPPORTED_LANGUAGES:
            return ToolResult(
                success=False,
                error=(
                    f"Unsupported language: {language}. "
                    f"Supported: {', '.join(SUPPORTED_LANGUAGES)}"
                ),
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )

        try:
            timeout_sec = int(timeout)
        except (TypeError, ValueError):
            return ToolResult(
                success=False,
                error="Invalid timeout.",
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )
        timeout_sec = max(1, min(timeout_sec, 300))

        try:
            import config
            api_key = config.E2B_API_KEY
            if not api_key:
                return ToolResult(
                    success=False,
                    error="E2B_API_KEY is not configured.",
                    tool_name=self.name,
                    execution_mode="real",
                    verified=False,
                )
        except Exception as e:
            logger.warning("E2B config check failed: %s", e, exc_info=True)
            return ToolResult(
                success=False,
                error="E2B sandbox is not configured.",
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )

        try:
            from e2b import Sandbox
        except ImportError:
            logger.warning("e2b package not installed", exc_info=True)
            return ToolResult(
                success=False,
                error="E2B SDK is not installed. Run: pip install e2b",
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )

        sandbox = None
        try:
            sandbox = Sandbox(api_key=api_key)

            if files:
                for fname, fcontent in files.items():
                    sandbox.file.write(f"/home/user/{fname}", fcontent)

            if lang == "python":
                result = sandbox.run_code(code, timeout=timeout_sec)
                output = result.stdout or ""
                error = result.stderr or ""
            elif lang == "javascript":
                result = sandbox.run_code(code, language="js", timeout=timeout_sec)
                output = result.stdout or ""
                error = result.stderr or ""
            else:
                result = sandbox.run_code(code, language=lang, timeout=timeout_sec)
                output = result.stdout or ""
                error = result.stderr or ""

            duration = int((time.time() - start) * 1000)
            success = result.status == "success"
            return ToolResult(
                success=success,
                data={
                    "output": output,
                    "error": error,
                    "language": lang,
                    "status": result.status,
                },
                raw=output[:_MAX_CODE_LENGTH],
                duration_ms=duration,
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )
        except Exception as e:
            logger.warning("E2B code execution failed: %s", e, exc_info=True)
            duration = int((time.time() - start) * 1000)
            return ToolResult(
                success=False,
                error="Sandbox execution failed safely without details.",
                duration_ms=duration,
                tool_name=self.name,
                execution_mode="real",
                verified=False,
            )
        finally:
            if sandbox is not None:
                try:
                    sandbox.kill()
                except Exception:
                    pass
