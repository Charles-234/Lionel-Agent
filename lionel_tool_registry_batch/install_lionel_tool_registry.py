from pathlib import Path
from datetime import datetime
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = Path.cwd()

if not (PROJECT / "config.py").exists():
    raise SystemExit("Run this installer from the Lionel project root, e.g. D:\\phantom-agent")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = PROJECT / "backups" / f"tool_registry_{stamp}"
backup.mkdir(parents=True, exist_ok=False)

for rel in ("tools_registry", "tests/test_tool_registry.py"):
    src = PROJECT / rel
    if src.exists():
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

for rel in ("tools_registry", "tests/test_tool_registry.py"):
    src = ROOT / rel
    dst = PROJECT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)

subprocess.run(
    [sys.executable, "-m", "py_compile"] +
    [str(PROJECT / "tools_registry" / p) for p in ("base.py", "registry.py", "resolver.py", "__init__.py")],
    check=True,
)

result = subprocess.run(
    [sys.executable, "-m", "unittest", "tests.test_tool_registry", "-v"],
    cwd=PROJECT,
    text=True,
)
if result.returncode != 0:
    raise SystemExit(result.returncode)

print("SUCCESS: Tool Registry installed and tests passed.")
print(f"Backup: {backup}")
