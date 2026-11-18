import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from leadpilot.shared.db import init_db
from leadpilot.contexts.tenant import service as ts
init_db(); ts.seed(); print("db initialized + seeded")
