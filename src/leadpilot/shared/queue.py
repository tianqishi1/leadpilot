"""租约任务队列：claim/heartbeat/checkpoint/complete/fail + bulkhead（详细设计 §6.2）。"""
import datetime as dt, json
from sqlalchemy import select, update
from leadpilot.shared import tables as T
from leadpilot.shared.db import tx, utcnow
from leadpilot.shared.ids import new_id, idem, env
CAPS = {"crawl": 2, "research": 3, "content": 2, "digest": 1, "dispatch": 1, "cleanup": 1, "eval": 1}
def now(): return utcnow()
def enqueue(kind, payload=None, tenant_id=None, idem_key=None, next_run_at=None):
    key = idem_key or idem(kind, json.dumps(payload or {}, sort_keys=True, default=str))
    with tx() as s:
        try:
            s.execute(T.job_queue.insert().values(id=new_id(), tenant_id=tenant_id, kind=kind, payload=payload or {},
                idempotency_key=key, next_run_at=next_run_at or now()))
            return key
        except Exception:
            return None  # 已存在同幂等 job
def claim(kinds, owner, lease_s=60):
    with tx() as s:
        rows = s.execute(select(T.job_queue).where(
            ((T.job_queue.c.status == "ready") & (T.job_queue.c.next_run_at <= now())) |
            ((T.job_queue.c.status == "leased") & (T.job_queue.c.lease_until < now()))
        ).order_by(T.job_queue.c.next_run_at).limit(50)).mappings().all()
        picked = []
        alive = {k: 0 for k in kinds}
        for r in s.execute(select(T.job_queue.c.kind).where(T.job_queue.c.status == "leased",
                T.job_queue.c.lease_until >= now())).all():
            alive[r[0]] = alive.get(r[0], 0) + 1
        for r in rows:
            k = r["kind"]
            if k not in kinds: continue
            if alive.get(k, 0) >= CAPS.get(k, 1): continue
            s.execute(update(T.job_queue).where(T.job_queue.c.id == r["id"]).values(
                status="leased", lease_owner=owner, lease_until=now() + dt.timedelta(seconds=lease_s),
                attempts=r["attempts"] + 1))
            alive[k] = alive.get(k, 0) + 1
            picked.append(dict(r))
            if len(picked) >= 5: break
        return picked
def heartbeat(job_id, owner, lease_s=60):
    with tx() as s:
        n = s.execute(update(T.job_queue).where(T.job_queue.c.id == job_id, T.job_queue.c.lease_owner == owner,
            T.job_queue.c.status == "leased").values(lease_until=now() + dt.timedelta(seconds=lease_s))).rowcount
        return n == 1
def checkpoint(job_id, owner, cp):
    with tx() as s:
        r = s.execute(select(T.job_queue.c.checkpoint).where(T.job_queue.c.id == job_id)).first()
        merged = {**(r[0] or {}), **cp}
        s.execute(update(T.job_queue).where(T.job_queue.c.id == job_id, T.job_queue.c.lease_owner == owner).values(checkpoint=merged))
def complete(job_id, owner):
    with tx() as s:
        s.execute(update(T.job_queue).where(T.job_queue.c.id == job_id, T.job_queue.c.lease_owner == owner).values(status="done"))
def fail(job_id, owner, err):
    with tx() as s:
        r = s.execute(select(T.job_queue).where(T.job_queue.c.id == job_id)).mappings().first()
        if not r: return
        if r["attempts"] >= r["max_attempts"]:
            s.execute(update(T.job_queue).where(T.job_queue.c.id == job_id).values(status="dead", last_error=str(err)[:500]))
        else:
            back = min(1800, 30 * (2 ** r["attempts"]))
            s.execute(update(T.job_queue).where(T.job_queue.c.id == job_id).values(
                status="ready", lease_owner=None, lease_until=None, last_error=str(err)[:500],
                next_run_at=now() + dt.timedelta(seconds=back)))
