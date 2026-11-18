import argparse, sys, pathlib, os
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from leadpilot.shared import envfile
envfile.load(ROOT)
from leadpilot.worker import main as w
ap = argparse.ArgumentParser(); ap.add_argument("--job", required=True, choices=list(w.HANDLERS)); ap.add_argument("--tenant", default=None); ap.add_argument("--live", action="store_true")
a = ap.parse_args()
if a.live: os.environ["SIGNAL_MODE"] = "live"
print(w.run_once(a.job, a.tenant))
