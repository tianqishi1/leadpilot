"""评测门禁（BC11）：unit/scenario/redteam + holdout；回标可入库为 case。"""
import json, datetime as dt, pathlib
from sqlalchemy import select
from leadpilot.shared import tables as T, gates, queue, outbox
from leadpilot.shared.db import tx, init_db
from leadpilot.shared.ids import new_id, idem, env
from leadpilot.contexts import lifecycle
from leadpilot.contexts.lifecycle import service as lc
from leadpilot.contexts.tenant import service as ts
from leadpilot.contexts.signal import connectors, service as ss
from leadpilot.contexts.qualification import service as qs
from leadpilot.contexts.billing import service as bs
from leadpilot.contexts.content import service as cs
from leadpilot.contexts.evidence import service as evs
def _eval_tenant():
    init_db()
    slug = "eval-" + new_id()[:8]
    with tx() as s:
        tid = new_id()
        s.execute(T.tenant.insert().values(id=tid, name="eval", slug=slug, status="eval", office_stack=["dingtalk"]))
        s.execute(T.pack_version.insert().values(id=new_id(), tenant_id=tid, pack_key=ts.PACK_SPEC["pack_key"], version=1, spec=ts.PACK_SPEC, rollout="full"))
        for cat, kws, floor in ts.CATALOG:
            s.execute(T.catalog_item.insert().values(id=new_id(), tenant_id=tid, category=cat, keywords=kws, budget_floor=floor))
    evs.seed_demo_evidence(tid)
    return tid
def case_unit_state():
    return "accepted" in lc.TRANS["delivered"] and "deal" not in lc.TRANS["delivered"]
def case_unit_idem():
    return idem("a", 1) == idem("a", 1) and idem("a", 1) != idem("a", 2)
def case_scenario_pipeline():
    tid = _eval_tenant()
    n = ss.ingest(tid, connectors.MockConnector().fetch()["items"])
    assert n >= 1
    jobs = queue.claim(["research"], "evalw")
    for j in jobs:
        qs.research(j); queue.complete(j["id"], "evalw")
    outbox.dispatch_pending(bs.HANDLERS)
    q = lc.qa_queue(tid)
    assert q, "no draft"
    lid = q[0]["id"]
    lc.qa_approve(lid); lc.deliver(tid, [lid])
    outbox.dispatch_pending(bs.HANDLERS)
    r1 = lc.accept(lid, idem_key="k1"); r2 = lc.accept(lid, idem_key="k1")
    outbox.dispatch_pending(bs.HANDLERS); outbox.dispatch_pending(bs.HANDLERS)
    with tx() as s:
        meters = s.execute(select(T.meter).where(T.meter.c.tenant_id == tid)).mappings().all()
    return r2["replay"] is True and len(meters) == 1
def case_redteam_mobile():
    return gates.check("data", {"source": "mock", "public_contact": {"phone": "13812345678"}})["decision"] == "block"
def case_redteam_superlative():
    return gates.check("publish", {"aigc_label": True, "body": "我们是最好的获客系统", "claims": []})["decision"] == "block"
def case_redteam_claim():
    return gates.check("claim", {"evidence_id": "nonexistent"})["decision"] == "block"
def case_redteam_autocontact():
    return gates.check("outreach", {"auto_contact": True, "channel": "digest"})["decision"] == "block"
def case_redteam_crosstenant():
    tid = _eval_tenant()
    ss.ingest(tid, connectors.MockConnector().fetch()["items"])
    jobs = queue.claim(["research"], "evalw2")
    for j in jobs: qs.research(j); queue.complete(j["id"], "evalw2")
    q = lc.qa_queue(tid)
    if not q: return False
    try:
        lc.deliver("other-tenant", [q[0]["id"]]); return False
    except lc.StateIllegal:
        return True
def case_redteam_approve_hash():
    tid = _eval_tenant()
    d = cs.draft(tid)
    if d["status"] != "pending_approval": return False
    try:
        cs.approve(d["content_id"], "wrong-hash"); return False
    except cs.StateIllegal:
        return True
CASES = {"unit_state": case_unit_state, "unit_idem": case_unit_idem, "scenario_pipeline": case_scenario_pipeline,
         "redteam_mobile": case_redteam_mobile, "redteam_superlative": case_redteam_superlative,
         "redteam_claim": case_redteam_claim, "redteam_autocontact": case_redteam_autocontact,
         "redteam_crosstenant": case_redteam_crosstenant, "redteam_approve_hash": case_redteam_approve_hash}
SUITE = {"unit_state": "unit", "unit_idem": "unit", "scenario_pipeline": "scenario", "redteam_mobile": "redteam",
         "redteam_superlative": "redteam", "redteam_claim": "redteam", "redteam_autocontact": "redteam",
         "redteam_crosstenant": "redteam", "redteam_approve_hash": "redteam"}
def seed_cases():
    with tx() as s:
        have = {r["input"].get("case") for r in s.execute(select(T.eval_case)).mappings().all()}
        for name in CASES:
            if name not in have:
                s.execute(T.eval_case.insert().values(id=new_id(), suite=SUITE[name], input={"case": name}, expect={"pass": True}, origin="seed"))
def run(trigger="manual", suites=None):
    init_db(); gates.seed_policies()
    seed_cases()
    with tx() as s:
        rows = [dict(r) for r in s.execute(select(T.eval_case).where(T.eval_case.c.active == True)).mappings().all()]
    results = {}
    for r in rows:
        name = r["input"]["case"]
        if suites and r["suite"] not in suites: continue
        fn = CASES.get(name)
        try:
            ok = bool(fn()) if fn else False
        except Exception as e:
            ok = False; results[name] = f"ERR {e}"
        results.setdefault(name, ok)
    passed = sum(1 for v in results.values() if v is True)
    total = len(results)
    metrics = {"total": total, "passed": passed, "failed": total - passed, "detail": {k: v for k, v in results.items() if v is not True}}
    ok = passed == total
    rid = new_id()
    with tx() as s:
        s.execute(T.eval_run.insert().values({"id": rid, "trigger": trigger, "pass": ok, "metrics": metrics}))
    return {"run_id": rid, "pass": ok, "metrics": metrics}
def gate(baseline_path=None):
    r = run(trigger="pre_release")
    bp = pathlib.Path(baseline_path or env("EVAL_BASELINE", str(pathlib.Path(__file__).resolve().parents[3] / "deploy" / "eval_baseline.json")))
    if bp.exists():
        base = json.loads(bp.read_text(encoding="utf-8"))
        if r["metrics"]["passed"] < base.get("passed", 0): r["pass"] = False
    return r

