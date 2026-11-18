"""线索生命周期与验收（BC4 core）：状态机/48h窗/补换。验收=计费=训练 三位一体入口。"""
import datetime as dt
from sqlalchemy import select, update
from leadpilot.shared import tables as T, events
from leadpilot.shared.db import tx, utcnow
from leadpilot.shared.ids import new_id, idem
TRANS = {"draft": ["ready", "dropped"], "ready": ["delivered"], "delivered": ["accepted", "invalid"],
         "accepted": ["contacted"], "contacted": ["opportunity"], "opportunity": ["deal"],
         "invalid": ["replaced"], "remediation": []}
class StateIllegal(Exception): pass
class WindowExpired(Exception): pass
def now(): return utcnow()
def _get(s, lid):
    r = s.execute(select(T.lead).where(T.lead.c.id == lid)).mappings().first()
    if not r: raise StateIllegal("lead not found")
    return dict(r)
def _move(s, lead, to, actor, idem_key, payload=None):
    if to not in TRANS.get(lead["status"], []):
        raise StateIllegal(f"{lead['status']}->{to}")
    s.execute(update(T.lead).where(T.lead.c.id == lead["id"]).values(status=to, updated_at=now()))
    etype = {"ready": None, "delivered": "LeadDelivered", "accepted": "LeadAccepted", "invalid": "LeadInvalidated",
             "contacted": "OpportunityReported", "opportunity": "OpportunityReported", "deal": "DealClosed",
             "replaced": "LeadReplaced", "dropped": None}.get(to)
    eid = new_id()
    if etype:
        s.execute(T.lead_event.insert().values(id=eid, lead_id=lead["id"], tenant_id=lead["tenant_id"], type=etype,
            payload=payload or {}, actor=actor, idempotency_key=idem_key))
        events.publish(s, etype, lead["id"], {"lead_id": lead["id"], "lead_event_id": eid, "actor": actor, **(payload or {})}, lead["tenant_id"], idem_key=idem_key)
    return eid
def qa_approve(lid, actor="owner"):
    with tx() as s:
        l = _get(s, lid); _move(s, l, "ready", actor, idem("qa", lid))
def qa_drop(lid, reason, actor="owner"):
    with tx() as s:
        l = _get(s, lid); _move(s, l, "dropped", actor, idem("drop", lid), {"reason": reason})
def deliver(tid, lids, actor="system"):
    out = []
    with tx() as s:
        for lid in lids:
            l = _get(s, lid)
            if l["tenant_id"] != tid: raise StateIllegal("cross-tenant")
            due = now() + dt.timedelta(hours=48)
            s.execute(update(T.lead).where(T.lead.c.id == lid).values(delivered_at=now(), acceptance_due_at=due))
            _move(s, {**l, "status": "ready"}, "delivered", actor, idem("deliver", lid), {"acceptance_due_at": str(due)})
            out.append(lid)
    return out
def accept(lid, actor="sales", idem_key=None):
    key = idem_key or idem("accept", lid)
    with tx() as s:
        l = _get(s, lid)
        ev = s.execute(select(T.lead_event).where(T.lead_event.c.lead_id == lid, T.lead_event.c.type == "LeadAccepted",
            T.lead_event.c.idempotency_key == key)).mappings().first()
        if ev:  # 幂等重放: 返回首次结果
            return {"lead_id": lid, "status": "accepted", "replay": True}
        if l["status"] != "delivered": raise StateIllegal(f"accept from {l['status']}")
        if l["acceptance_due_at"] and l["acceptance_due_at"] < now(): raise WindowExpired("48h window expired")
        _move(s, l, "accepted", actor, key)
    return {"lead_id": lid, "status": "accepted", "replay": False}
def invalidate(lid, reason_code, note="", actor="sales", idem_key=None):
    if not reason_code: raise ValueError("reason required")
    key = idem_key or idem("invalid", lid)
    with tx() as s:
        l = _get(s, lid)
        if s.execute(select(T.lead_event).where(T.lead_event.c.lead_id == lid, T.lead_event.c.type == "LeadInvalidated",
                T.lead_event.c.idempotency_key == key)).first():
            return {"lead_id": lid, "status": "invalid", "replay": True}
        if l["status"] != "delivered": raise StateIllegal(f"invalidate from {l['status']}")
        _move(s, l, "invalid", actor, key, {"reason_code": reason_code, "note": note})
        due = now() + dt.timedelta(hours=48)
        s.execute(T.replacement_case.insert().values(id=new_id(), tenant_id=l["tenant_id"], lead_id=lid,
            reason=f"{reason_code}:{note}", due_at=due))
    return {"lead_id": lid, "status": "invalid", "replacement_due": str(due)}
def stage(lid, to, actor="sales", note="", idem_key=None):
    with tx() as s:
        l = _get(s, lid); _move(s, l, to, actor, idem_key or idem("stage", lid, to), {"note": note})
def fulfill_replacements(payload, event):
    lid = payload["lead_id"]; tid = event["tenant_id"]
    with tx() as s:
        l = s.execute(select(T.lead).where(T.lead.c.id == lid)).mappings().first()
        if not l: return
        cases = s.execute(select(T.replacement_case).where(T.replacement_case.c.tenant_id == tid,
            T.replacement_case.c.status == "open")).mappings().all()
        for c in cases:
            old = s.execute(select(T.lead).where(T.lead.c.id == c["lead_id"])).mappings().first()
            if old and old["company_id"] == l["company_id"] and c["created_at"] <= l["delivered_at"]:
                s.execute(update(T.replacement_case).where(T.replacement_case.c.id == c["id"]).values(
                    status="fulfilled", replacement_lead_id=lid))
def qa_queue(tid):
    with tx() as s:
        return [dict(r) for r in s.execute(select(T.lead).where(T.lead.c.tenant_id == tid, T.lead.c.status == "draft")
            .order_by(T.lead.c.created_at)).mappings().all()]
def pool(tid, status=None):
    with tx() as s:
        q = select(T.lead).where(T.lead.c.tenant_id == tid)
        if status: q = q.where(T.lead.c.status == status)
        return [dict(r) for r in s.execute(q.order_by(T.lead.c.created_at.desc())).mappings().all()]
def open_replacements(tid):
    with tx() as s:
        return [dict(r) for r in s.execute(select(T.replacement_case).where(T.replacement_case.c.tenant_id == tid,
            T.replacement_case.c.status == "open")).mappings().all()]
