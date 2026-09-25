"""Start the dashboard backend as a detached subprocess."""
import subprocess
import sys
import os

port = sys.argv[1] if len(sys.argv) > 1 else "8090"

# Start uvicorn detached
subprocess.Popen(
    [os.environ.get("VIRTUAL_ENV", "D:\\Phantom-agent\\.venv") + "\\Scripts\\python.exe",
     "-m", "uvicorn", "dashboard_backend:app",
     "--host", "0.0.0.0", "--port", port],
    cwd="D:\\Phantom-agent",
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
print(f"Started on port {port}")
