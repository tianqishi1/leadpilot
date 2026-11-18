"""outbox dispatcher：at-least-once + handler 幂等兜底（详细设计 §6.1）。"""
import datetime as dt, logging
from sqlalchemy import select, update
from leadpilot.shared import tables as T
from leadpilot.shared.db import tx, utcnow
log = logging.getLogger("outbox")
def dispatch_pending(handlers, limit=50):
    with tx() as s:
        rows = s.execute(select(T.outbox).where(T.outbox.c.dispatched_at.is_(None))
            .order_by(T.outbox.c.occurred_at).limit(limit)).mappings().all()
    done = 0
    for r in rows:
        h = handlers.get(r["event_type"])
        try:
            if h: h(dict(r["payload"]), dict(r))
            with tx() as s:
                s.execute(update(T.outbox).where(T.outbox.c.id == r["id"]).values(dispatched_at=utcnow()))
            done += 1
        except Exception as e:
            log.warning("outbox handler fail %s %s: %s", r["event_type"], r["id"], e)
            with tx() as s:
                att = r["attempts"] + 1
                vals = {"attempts": att}
                if att >= 10:
                    vals["dispatched_at"] = utcnow()  # dead-letter: 告警由 metrics 暴露
                    log.error("outbox dead-letter %s %s", r["event_type"], r["id"])
                s.execute(update(T.outbox).where(T.outbox.c.id == r["id"]).values(**vals))
    return done
