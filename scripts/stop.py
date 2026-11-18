import json, pathlib, os, signal, sys, subprocess
ROOT = pathlib.Path(__file__).resolve().parents[1]
p = ROOT / "var" / "pids.json"
if not p.exists():
    print("no pids"); sys.exit(0)
for name, pid in json.loads(p.read_text()).items():
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True); print("stopped", name, pid)
    except ProcessLookupError:
        print("already gone", name, pid)
p.unlink()
