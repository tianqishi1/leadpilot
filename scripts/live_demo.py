"""live 演示租户：全国切片(region=[])跑真实政采源, 证明 live 链路; 生产租户 own 保持长三角切片。"""
import sys, pathlib, os, json
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from leadpilot.shared import envfile
envfile.load(ROOT)
from leadpilot.shared import envfile as _ef
_ef.load(ROOT)
os.environ["SIGNAL_MODE"] = "live"
from leadpilot.shared.db import init_db, tx
from leadpilot.shared import tables as T
from leadpilot.shared.ids import new_id
from leadpilot.contexts.tenant import service as ts
from leadpilot.worker import main as w
from leadpilot.contexts.lifecycle import service as lc
init_db(); ts.seed()
with tx() as s:
    row = s.execute(T.tenant.select().where(T.tenant.c.slug == "live-demo")).mappings().first()
    if row:
        tid = row["id"]
    else:
        tid = new_id()
        spec = json.loads(json.dumps(ts.PACK_SPEC)); spec["region"] = []
        s.execute(T.tenant.insert().values(id=tid, name="live 演示(政采口径/全国)", slug="live-demo", office_stack=["dingtalk"]))
        s.execute(T.pack_version.insert().values(id=new_id(), tenant_id=tid, pack_key=spec["pack_key"], version=1, spec=spec, rollout="full"))
        for cat, kws, floor in [("政采设备", ["设备", "系统", "洗衣", "医疗", "仪器"], 10000), ("政采服务", ["服务", "运营", "物业", "保洁"], 10000)]:
            s.execute(T.catalog_item.insert().values(id=new_id(), tenant_id=tid, category=cat, keywords=kws, budget_floor=floor))
print("live-demo tenant", tid)
print("crawl:", w.run_once("crawl", tid))
print("research:", w.run_once("research", tid))
q = lc.qa_queue(tid)
print("REAL draft cards:", len(q))
for x in q:
    print("  REAL:", x["card"]["company"], "|", x["card"]["project"][:46], "|", x["stage"], "| score", x["score"], "| evidence", len(x["card"]["evidence"]))
