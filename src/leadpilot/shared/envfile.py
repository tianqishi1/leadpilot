"""简易 .env 加载（无第三方依赖）。凭据只进 .env(gitignored), 不进 repo/日志。"""
import os, pathlib
def load(root=None):
    root = pathlib.Path(root or pathlib.Path(__file__).resolve().parents[2])
    f = root / ".env"
    if not f.exists(): return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()  # .env 为项目配置, 覆盖继承环境
