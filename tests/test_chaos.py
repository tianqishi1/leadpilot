"""chaos：租约续跑不双计费 / accept 幂等 / outbox 重复 dispatch 单 meter。"""
import datetime as dt
from sqlalchemy import update, select
from leadpilot.shared import tables as T, queue, outbox
from leadpilot.shared.db import tx, utcnow
from leadpilot.contexts.tenant import service as ts
from leadpilot.contexts.signal import connectors, service as ss
from leadpilot.contexts.qualification import service as qs
from leadpilot.contexts.lifecycle import service as lc
from leadpilot.contexts.billing import service as bs
def _pipeline(tid):
    ss.ingest(tid, connectors.MockConnector().fetch()["items"])
    jobs = queue.claim(["research"], "chaos1")
    for j in jobs:
        qs.research(j)  # 故意不 complete, 模拟 kill -9
    return jobs
def test_lease_resume_no_double(tid):
    jobs = _pipeline(tid)
    with tx() as s:  # 模拟 kill -9: lease 过期
        s.execute(update(T.job_queue).where(T.job_queue.c.status == "leased").values(lease_until=utcnow() - dt.timedelta(seconds=1)))
    resumed = queue.claim(["research"], "chaos2")
    for j in resumed:
        qs.research(j); queue.complete(j["id"], "chaos2")
    outbox.dispatch_pending(bs.HANDLERS)
    q = lc.qa_queue(tid)
    lc.qa_approve(q[0]["id"]); lc.deliver(tid, [q[0]["id"]])
    lc.accept(q[0]["id"], idem_key="chaos-k")
    outbox.dispatch_pending(bs.HANDLERS); outbox.dispatch_pending(bs.HANDLERS)
    with tx() as s:
        meters = s.execute(select(T.meter).where(T.meter.c.lead_id == q[0]["id"])).mappings().all()
        leads = s.execute(select(T.lead).where(T.lead.c.tenant_id == tid)).mappings().all()
    assert len(meters) == 1
    assert len(leads) == len({l["idempotency_key"] for l in leads}) and len(leads) >= 2  # 续跑不产生重复 lead 卡
def test_accept_replay_single_meter(tid):
    q = lc.pool(tid, "accepted")
    lid = q[0]["id"]
    r = lc.accept(lid, idem_key="chaos-k")
    assert r["replay"] is True
    outbox.dispatch_pending(bs.HANDLERS)
    with tx() as s:
        n = s.execute(select(T.meter).where(T.meter.c.lead_id == lid)).mappings().all()
    assert len(n) == 1
def test_window_expired(tid):
    ss.ingest(tid, connectors.MockConnector().fetch()["items"])
    jobs = queue.claim(["research"], "chaos3")
    for j in jobs: qs.research(j); queue.complete(j["id"], "chaos3")
    q = lc.qa_queue(tid)
    if not q: return
    lid = q[0]["id"]; lc.qa_approve(lid); lc.deliver(tid, [lid])
    with tx() as s:
        s.execute(update(T.lead).where(T.lead.c.id == lid).values(acceptance_due_at=utcnow() - dt.timedelta(hours=1)))
    try:
        lc.accept(lid); assert False
    except lc.WindowExpired:
        pass
