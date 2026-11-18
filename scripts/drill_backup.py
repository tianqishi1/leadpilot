"""备份恢复演练：sqlite 复制+行数校验；PG 提示 pg_dump/恢复命令。RPO<=24h 纪律。"""
import sys, pathlib, shutil, datetime as dt, sqlite3
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from leadpilot.shared.db import URL, IS_PG
def main():
    if IS_PG:
        print("PG: 使用 RDS 自动备份; 演练命令: pg_dump $DATABASE_URL > var/backup.sql && 恢复到临时实例后校验行数")
        return
    src = pathlib.Path(URL.replace("sqlite:///", ""))
    dst = ROOT / "var" / f"backup-drill-{dt.datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(src, dst)
    a = sqlite3.connect(src); b = sqlite3.connect(dst)
    tables = ["lead", "lead_event", "meter", "outbox", "evidence_record"]
    ok = True
    for t in tables:
        try:
            ca = a.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            cb = b.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(t, ca, cb, "OK" if ca == cb else "MISMATCH"); ok &= ca == cb
        except sqlite3.OperationalError:
            print(t, "skip")
    print("drill", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
if __name__ == "__main__":
    main()
