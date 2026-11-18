import argparse, sys, pathlib, json, os, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from leadpilot.shared import envfile
envfile.load(ROOT)
# ISOLATED: 评测用独立 DB, 避免与运行中 worker 竞争租约
os.environ["MODEL_PROVIDER"] = "mock"
os.environ["SIGNAL_MODE"] = "mock"
os.environ["HEADLESS"] = "0"
os.environ["DATABASE_URL"] = "sqlite:///" + str(pathlib.Path(tempfile.mkdtemp(prefix="lp-eval-")) / "eval.db")
from leadpilot.contexts.evals import runner
ap = argparse.ArgumentParser(); ap.add_argument("--gate", action="store_true"); ap.add_argument("--suites", default=None)
a = ap.parse_args()
r = runner.gate() if a.gate else runner.run(suites=a.suites.split(",") if a.suites else None)
print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
sys.exit(0 if r["pass"] else 1)
