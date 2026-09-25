from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = Path.cwd()
BACKUP = PROJECT / "backups" / (
    "audit_integration_" + datetime.now().strftime("%Y%m%d_%H%M%S")
)

required = [
    PROJECT / "audit" / "ledger.py",
    PROJECT / "tools" / "registry.py",
    ROOT / "audit" / "integration.py",
    ROOT / "tools" / "executor.py",
    ROOT / "tests" / "test_audit_integration.py",
]
missing = [str(p) for p in required if not p.exists()]
if missing:
    print("ERROR: prerequisites missing:")
    print("\n".join(missing))
    raise SystemExit(1)

for rel in ("tools/executor.py", "tests/test_audit_integration.py"):
    dest = PROJECT / rel
    if dest.exists():
        backup = BACKUP / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, backup)

(PROJECT / "audit").mkdir(exist_ok=True)
(PROJECT / "tests").mkdir(exist_ok=True)

shutil.copy2(ROOT / "audit" / "integration.py", PROJECT / "audit" / "integration.py")
shutil.copy2(ROOT / "tools" / "executor.py", PROJECT / "tools" / "executor.py")
shutil.copy2(ROOT / "tests" / "test_audit_integration.py", PROJECT / "tests" / "test_audit_integration.py")

subprocess.run(
    [sys.executable, "-m", "py_compile",
     str(PROJECT / "audit" / "integration.py"),
     str(PROJECT / "tools" / "executor.py"),
     str(PROJECT / "tests" / "test_audit_integration.py")],
    check=True,
)
subprocess.run(
    [sys.executable, "-m", "unittest", "tests.test_audit_integration", "-v"],
    check=True,
)

print("SUCCESS: Lionel audit integration installed and tests passed.")
print(f"Backup: {BACKUP}")
