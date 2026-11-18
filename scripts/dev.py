import os, sys, pathlib, subprocess, json, signal
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from leadpilot.shared import envfile
envfile.load(ROOT)
os.environ.setdefault("PYTHONPATH", str(ROOT / "src"))
from leadpilot.shared.db import init_db
from leadpilot.contexts.tenant import service as ts
def main():
    init_db(); ts.seed()
    (ROOT / "var").mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    logs = {}
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "leadpilot.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
                           cwd=ROOT, env=env, stdout=open(ROOT / "var" / "api.log", "w"), stderr=subprocess.STDOUT)
    wk = subprocess.Popen([sys.executable, "-m", "leadpilot.worker.main"], cwd=ROOT, env=env,
                          stdout=open(ROOT / "var" / "worker.log", "w"), stderr=subprocess.STDOUT)
    (ROOT / "var" / "pids.json").write_text(json.dumps({"api": api.pid, "worker": wk.pid}))
    print(f"api pid={api.pid} http://127.0.0.1:8000/  (login: ADMIN_PASSWORD)")
    print(f"worker pid={wk.pid}")
    print("logs: var/api.log var/worker.log ; stop: python scripts/stop.py")
if __name__ == "__main__":
    main()
