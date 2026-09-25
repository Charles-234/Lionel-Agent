from pathlib import Path
from datetime import datetime
import shutil, subprocess, sys

PROJECT = Path(r"D:\phantom-agent")
BUNDLE = PROJECT / "lionel_architecture_v1" / "lionel_architecture_v1"
FILES = ["tools/base.py","tools/policy.py","tools/registry.py","tools/executor.py","tools/mocks.py","tools/recon/subfinder.py","tools/recon/httpx.py","tools/recon/nuclei.py","chains/recon.py","tests/test_governed_tools.py"]

if not PROJECT.exists(): raise SystemExit(f"Project not found: {PROJECT}")
if not BUNDLE.exists(): raise SystemExit(f"Extracted architecture bundle not found: {BUNDLE}")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = PROJECT / "backups" / f"governance_{stamp}"
backup.mkdir(parents=True, exist_ok=True)
for rel in FILES:
    src = PROJECT / rel
    if src.exists():
        dst = backup / rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)

for rel in ["tools/base.py","tools/policy.py","tools/executor.py","chains/recon.py","tests/test_governed_tools.py"]:
    src, dst = BUNDLE / rel, PROJECT / rel
    dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)

registry = '''"""Central governed registry for Lionel tools."""
from dataclasses import dataclass
from typing import Any, Dict, Optional
from tools.base import Tool, ToolResult
from tools.policy import AuthorizationScope, PolicyGateway

@dataclass
class ToolRecord:
    tool: Tool
    enabled: bool = True
    source: str = "builtin"

class ToolRegistry:
    def __init__(self, policy: Optional[PolicyGateway] = None):
        self.policy = policy or PolicyGateway()
        self._records: Dict[str, ToolRecord] = {}

    def register(self, tool: Tool, *, source: str = "builtin", enabled: bool = True) -> None:
        if not tool.name: raise ValueError("Tool must have a name")
        if tool.name in self._records: raise ValueError(f"Tool already registered: {tool.name}")
        self._records[tool.name] = ToolRecord(tool, enabled, source)

    def get(self, name: str) -> Tool:
        record = self._records.get(name)
        if not record or not record.enabled: raise KeyError(f"Tool unavailable: {name}")
        return record.tool

    def list(self) -> list[Dict[str, Any]]:
        return [{**r.tool.manifest(), "enabled": r.enabled, "registry_source": r.source} for r in self._records.values()]

    def authorize_and_run(self, name: str, arguments: Dict[str, Any], *, scope: Optional[AuthorizationScope] = None, execution_mode: str = "real", confirmed: bool = False) -> ToolResult:
        tool = self.get(name)
        decision = self.policy.evaluate(tool, arguments, scope, execution_mode, confirmed)
        if not decision.allowed:
            return ToolResult(False, error=decision.reason, tool_name=name, execution_mode=execution_mode, verified=False)
        if execution_mode == "simulation":
            from tools.mocks import MOCK_TOOLS
            mock_cls = MOCK_TOOLS.get(name)
            if not mock_cls:
                return ToolResult(False, error="Simulation implementation is unavailable.", tool_name=name, execution_mode="simulation", verified=False)
            result = mock_cls().run(**arguments)
            result.execution_mode = "simulation"; result.verified = False
            if not result.evidence: result.evidence = [{"source":"mock", "verified":False}]
            return result
        result = tool.run(**arguments)
        result.execution_mode = "real"
        result.verified = bool(decision.metadata.get("verified", False))
        return result

_default_registry: Optional[ToolRegistry] = None
def get_registry() -> ToolRegistry:
    global _default_registry
    if _default_registry is None:
        from tools.recon.subfinder import Subfinder
        from tools.recon.httpx import Httpx
        from tools.recon.nuclei import Nuclei
        _default_registry = ToolRegistry()
        for tool in (Subfinder(), Httpx(), Nuclei()): _default_registry.register(tool)
    return _default_registry
'''
(PROJECT / "tools/registry.py").write_text(registry, encoding="utf-8")

metadata = {
    "tools/recon/subfinder.py": ("subfinder", "medium", False),
    "tools/recon/httpx.py": ("httpx", "medium", False),
    "tools/recon/nuclei.py": ("nuclei", "high", True),
}
for rel, (name, risk, confirm) in metadata.items():
    p = PROJECT / rel; s = p.read_text(encoding="utf-8")
    anchor = f'    requires_binary = "{name}"'
    block = [f'    risk_level = "{risk}"','    requires_authorized_target = True','    network_access = True','    supports_simulation = True']
    if confirm: block.append('    confirmation_required = True')
    block.append('    provenance = "builtin"')
    missing = any(line not in s for line in block)
    if missing:
        # Remove an incomplete governance block if one exists, then add a canonical block.
        s = s.replace(anchor + "\n" + "\n".join(block), anchor, 1)
        s = s.replace(anchor, anchor + "\n" + "\n".join(block), 1)
    # Current known legacy fallback forms.
    if f'if not self.available():\n            logger.info(f"{name} not installed' in s:
        start = s.index(f'        if not self.available():', s.index('def run'))
        end = s.index('\n', s.index('return self._mock.run', start)) + 1
        s = s[:start] + '        if not self.available():\n            return ToolResult(success=False, error="Required tool binary is unavailable.", tool_name=self.name, execution_mode="real", verified=False)\n' + s[end:]
    p.write_text(s, encoding="utf-8")

p = PROJECT / "tools/mocks.py"; s = p.read_text(encoding="utf-8")
for cls in ["MockSubfinder", "MockHttpx", "MockNuclei"]:
    marker = f"class {cls}(Tool):"
    pos = s.find(marker)
    if pos < 0: raise SystemExit(f"Could not locate {cls}")
    end = s.find("\n\nclass ", pos + len(marker))
    if end < 0: end = len(s)
    block = s[pos:end]
    if "supports_simulation = True" not in block:
        needle = "    requires_binary = None"
        if needle not in block: raise SystemExit(f"Could not locate requires_binary for {cls}")
        block = block.replace(needle, needle + '\n    supports_simulation = True\n    provenance = "simulation"', 1)
        s = s[:pos] + block + s[end:]
# Ensure mock result provenance is explicit for existing result constructors.
s = s.replace('            tool_name=self.name,\n        )', '            tool_name=self.name,\n            execution_mode="simulation",\n            verified=False,\n            evidence=[{"source": "mock", "verified": False}],\n        )')
p.write_text(s, encoding="utf-8")

py_files = [str(PROJECT / rel) for rel in FILES if rel.endswith(".py")]
subprocess.run([sys.executable, "-m", "py_compile", *py_files], cwd=PROJECT, check=True)
subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_governed_tools.py", "-v"], cwd=PROJECT, check=True)
print(f"\nSUCCESS: governed tool layer installed and offline governance tests passed.\nBackup: {backup}")
