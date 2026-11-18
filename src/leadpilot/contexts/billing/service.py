"""计费与成本（BC5）+ outbox handlers 汇总。meter UNIQUE(lead_id)=每线索至多一次计费。"""
import datetime as dt, logging
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from leadpilot.shared import tables as T, events
from leadpilot.shared.db import tx, utcnow
from leadpilot.shared.ids import new_id, idem
from leadpilot.contexts.tenant import service as tenant
from leadpilot.contexts.lifecycle import service as lifecycle
from leadpilot.contexts.evidence import service as evidence
log = logging.getLogger("billing")
def on_accepted(payload, event):
    lid = payload["lead_id"]; tid = event["tenant_id"]
    cfg = tenant.config_snapshot(tid)
    price = float(((cfg["pack"] or {}).get("spec") or {}).get("billing", {}).get("price_rmb", 150))
    with tx() as s:
        try:
            s.execute(T.meter.insert().values(id=new_id(), tenant_id=tid, lead_id=lid,
                lead_event_id=payload.get("lead_event_id"), price_rmb=price, idempotency_key=idem("meter", lid)))
        except IntegrityError:
            log.info("meter duplicate skipped lead=%s", lid); return
        period = utcnow().strftime("%Y-%m")
        inv = s.execute(select(T.invoice).where(T.invoice.c.tenant_id == tid, T.invoice.c.period == period)).mappings().first()
        if inv:
            s.execute(update(T.invoice).where(T.invoice.c.id == inv["id"]).values(total_rmb=float(inv["total_rmb"]) + price))
        else:
            s.execute(T.invoice.insert().values(id=new_id(), tenant_id=tid, period=period, total_rmb=price))
def on_deal(payload, event):
    lid = payload["lead_id"]; tid = event["tenant_id"]
    with tx() as s:
        l = s.execute(select(T.lead).where(T.lead.c.id == lid)).mappings().first()
    if not l: return
    evidence.create_draft(tid, "case_metric", metric={"value": payload.get("amount"), "unit": "元",
        "period": utcnow().strftime("%Y-%m"), "baseline": "商家自报", "query_ref": f"lead:{lid}"},
        source_urls=(l["card"] or {}).get("evidence", []), tags=["成交候选"])
def on_delivered(payload, event):
    lifecycle.fulfill_replacements(payload, event)
def on_content_approved(payload, event):
    from leadpilot.shared import queue
    queue.enqueue("publish", {"content_id": payload["content_id"]}, event["tenant_id"],
                  idem_key=idem("publish", payload["content_id"]))
HANDLERS = {"LeadAccepted": on_accepted, "DealClosed": on_deal, "LeadDelivered": on_delivered,
            "EvidenceRevoked": evidence.on_revoked, "ContentApproved": on_content_approved}
def stats(tid):
    with tx() as s:
        leads = s.execute(select(T.lead.c.status).where(T.lead.c.tenant_id == tid)).all()
        meters = s.execute(select(T.meter).where(T.meter.c.tenant_id == tid)).mappings().all()
        costs = s.execute(select(T.cost_entry).where(T.cost_entry.c.tenant_id == tid)).mappings().all()
        repl = s.execute(select(T.replacement_case).where(T.replacement_case.c.tenant_id == tid)).mappings().all()
    from collections import Counter
    cnt = Counter(r[0] for r in leads)
    total_cost = sum(float(c["amount_rmb"]) for c in costs)
    accepted = cnt.get("accepted", 0) + cnt.get("contacted", 0) + cnt.get("opportunity", 0) + cnt.get("deal", 0)
    delivered = accepted + cnt.get("invalid", 0)
    return {"by_status": dict(cnt), "metered": len(meters), "revenue_rmb": sum(float(m["price_rmb"]) for m in meters),
            "cost_rmb": round(total_cost, 2), "cost_per_accepted": round(total_cost / accepted, 2) if accepted else None,
            "accept_rate": round(accepted / delivered, 3) if delivered else None,
            "repl_open": sum(1 for r in repl if r["status"] == "open"),
            "repl_breached": sum(1 for r in repl if r["status"] == "open" and r["due_at"] < utcnow())}


