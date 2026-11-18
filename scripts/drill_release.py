"""发布演练：eval 门禁 + chaos 子集。"""
import subprocess, sys, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[1]
r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_evals.py"), "--gate"], capture_output=True, text=True)
print(r.stdout[-2000:]); print("eval gate exit", r.returncode)
c = subprocess.run([sys.executable, "-m", "pytest", "-q", str(ROOT / "tests" / "test_chaos.py")], capture_output=True, text=True, cwd=ROOT)
print(c.stdout[-1500:]); print("chaos exit", c.returncode)
sys.exit(0 if r.returncode == 0 and c.returncode == 0 else 1)
