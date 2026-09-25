from pathlib import Path
from datetime import datetime
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = Path.cwd()

if not (PROJECT / "config.py").exists():
    raise SystemExit("Run this installer from the Lionel project root, e.g. D:\\phantom-agent")

required = [
    PROJECT / "tools" / "base.py",
    PROJECT / "tools" / "mocks.py",
    PROJECT / "tools" / "recon" / "subfinder.py",
    PROJECT / "tools" / "recon" / "httpx.py",
    PROJECT / "tools" / "recon" / "nuclei.py",
    PROJECT / "tools_registry" / "registry.py",
]
missing = [str(p) for p in required if not p.exists()]
if missing:
    raise SystemExit("Required previous-layer files are missing:\n" + "\n".join(missing))

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = PROJECT / "backups" / f"capability_gate_{stamp}"
backup.mkdir(parents=True, exist_ok=False)

for rel in ("tools/policy.py", "tools/registry.py", "tools/executor.py",
            "chains/recon.py", "tests/test_capability_gate.py"):
    src = PROJECT / rel
    if src.exists():
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

for rel in ("tools/policy.py", "tools/registry.py", "tools/executor.py", "chains/recon.py"):
    src = ROOT / rel
    dst = PROJECT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

shutil.copy2(ROOT / "tests/test_capability_gate.py",
             PROJECT / "tests/test_capability_gate.py")

compile_files = [
    PROJECT / "tools/policy.py",
    PROJECT / "tools/registry.py",
    PROJECT / "tools/executor.py",
    PROJECT / "chains/recon.py",
    PROJECT / "tests/test_capability_gate.py",
]
subprocess.run([sys.executable, "-m", "py_compile", *map(str, compile_files)], cwd=PROJECT, check=True)

result = subprocess.run(
    [sys.executable, "-m", "unittest", "tests.test_capability_gate", "-v"],
    cwd=PROJECT, text=True,
)
if result.returncode:
    raise SystemExit(result.returncode)

print("SUCCESS: Capability-aware Policy Gateway installed and tests passed.")
print(f"Backup: {backup}")
