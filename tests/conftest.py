import os, pathlib, tempfile, pytest
TMP = pathlib.Path(tempfile.mkdtemp(prefix="leadpilot-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP/'test.db'}"
os.environ["MODEL_PROVIDER"] = "mock"
os.environ["SIGNAL_MODE"] = "mock"
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from leadpilot.shared.db import init_db
from leadpilot.contexts.tenant import service as ts
@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db(); ts.seed()
@pytest.fixture()
def tid():
    return ts.tenant_by_slug("merchant-demo")["id"]
