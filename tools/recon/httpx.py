"""
HTTPX adapter - HTTP probing at scale.

Falls back to MockHttpx when the binary is not installed.
"""
import json
import logging
import shutil
import subprocess
import time
from typing import Any, Dict, List

from tools.base import Tool, ToolResult
from tools.mocks import MockHttpx

logger = logging.getLogger(__name__)


class Httpx(Tool):
    name = "httpx"
    description = "Probe HTTP services on a list of hosts using httpx"
    category = "recon"
    requires_binary = "httpx"

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
        if not hosts:
            return ToolResult(success=True, data={"live_hosts": [], "count": 0},
                              tool_name=self.name)

        if not self.available():
            logger.info(f"httpx not installed - using mock for {len(hosts)} hosts")
            return self._mock.run(hosts=hosts)

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
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return ToolResult(success=False, error=str(e),
                              duration_ms=duration, tool_name=self.name)

        live = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                live.append({
                    "url": obj.get("url", ""),
                    "status_code": obj.get("status_code", 0),
                    "title": obj.get("title", ""),
                    "tech": obj.get("tech", []),
                    "port": obj.get("port", 0),
                })
            except json.JSONDecodeError:
                continue

        duration = int((time.time() - start) * 1000)
        return ToolResult(
            success=True,
            data={"live_hosts": live, "count": len(live)},
            raw=proc.stdout,
            duration_ms=duration,
            tool_name=self.name,
        )