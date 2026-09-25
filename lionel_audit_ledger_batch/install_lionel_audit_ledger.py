from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[0]
PROJECT = Path.cwd()
BACKUP = PROJECT / "backups" / (
    "audit_ledger_" + datetime.now().strftime("%Y%m%d_%H%M%S")
)

required = [
    ROOT / "audit" / "__init__.py",
    ROOT / "audit" / "ledger.py",
    ROOT / "tests" / "test_audit_ledger.py",
]
missing = [str(p) for p in required if not p.exists()]
if missing:
    print("ERROR: Missing batch files:")
    print("\n".join(missing))
    raise SystemExit(1)

for rel in ("audit/__init__.py", "audit/ledger.py", "tests/test_audit_ledger.py"):
    dest = PROJECT / rel
    if dest.exists():
        BACKUP.mkdir(parents=True, exist_ok=True)
        backup_dest = BACKUP / rel
        backup_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, backup_dest)

(PROJECT / "audit").mkdir(exist_ok=True)
(PROJECT / "tests").mkdir(exist_ok=True)

shutil.copy2(ROOT / "audit" / "__init__.py", PROJECT / "audit" / "__init__.py")
shutil.copy2(ROOT / "audit" / "ledger.py", PROJECT / "audit" / "ledger.py")
shutil.copy2(ROOT / "tests" / "test_audit_ledger.py", PROJECT / "tests" / "test_audit_ledger.py")

compile_targets = [
    PROJECT / "audit" / "ledger.py",
    PROJECT / "tests" / "test_audit_ledger.py",
]
subprocess.run(
    [sys.executable, "-m", "py_compile", *map(str, compile_targets)],
    check=True,
)
subprocess.run(
    [sys.executable, "-m", "unittest", "tests.test_audit_ledger", "-v"],
    check=True,
)

print("SUCCESS: Lionel SQLite audit ledger installed and tests passed.")
print(f"Backup: {BACKUP}")
