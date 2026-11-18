"""信号 ingest：数据门→归一→去重→TTL→ICP→评分→enqueue research（BC2）。"""
import datetime as dt, hashlib, logging
from sqlalchemy import select
from leadpilot.shared import tables as T, gates, queue, events
from leadpilot.shared.db import tx, utcnow
from leadpilot.shared.ids import new_id, idem
from leadpilot.contexts.tenant import service as tenant
log = logging.getLogger("signal")
def now(): return utcnow()
def ingest(tenant_id, items):
    cfg = tenant.config_snapshot(tenant_id)
    spec = (cfg["pack"] or {}).get("spec") or {}
    weights = {s["source"]: s for s in spec.get("signals", [])}
    created = 0
    for it in items:
        g = gates.check("data", {"source": it.get("source"), "public_contact": it.get("public_contact")}, tenant_id)
        if g["decision"] != "allow":
            log.info("data gate drop %s %s", it.get("project_name"), g["reasons"]); continue
        name = (it.get("company_name") or "").strip()
        if not name: continue
        with tx() as s:
            c = s.execute(select(T.company).where(T.company.c.tenant_id == tenant_id, T.company.c.name == name)).mappings().first()
            if not c:
                cid = new_id()
                s.execute(T.company.insert().values(id=cid, tenant_id=tenant_id, name=name, region=it.get("region") or ""))
            else:
                cid = c["id"]
        dedup = idem(cid, it.get("project_name"), it.get("source"))
        with tx() as s:
            if s.execute(select(T.signal).where(T.signal.c.tenant_id == tenant_id, T.signal.c.dedup_key == dedup)).first():
                continue
        stage = it.get("stage", "pre_bid")
        w = weights.get(it.get("source"), {"weight": 0.5, "ttl_days": 180})
        ttl_days = w.get("ttl_days", 180)
        if stage == "bid" and it.get("deadline"):
            try:
                dl = dt.date.fromisoformat(it["deadline"])
                ttl_at = dt.datetime.combine(dl, dt.time(23, 59))
            except ValueError:
                ttl_at = now() + dt.timedelta(days=ttl_days)
        else:
            ttl_at = now() + dt.timedelta(days=ttl_days)
        regions = spec.get("region") or []
        if regions and it.get("region") and it["region"] not in regions:
            continue  # 区域切片过滤
        text = (it.get("project_name", "") + " " + it.get("raw_text", ""))
        matched = [c for c in cfg["catalog"] if any(k in text for k in c["keywords"])]
        if not matched:
            continue  # ICP 不匹配丢弃
        floor = min(float(c["budget_floor"] or 0) for c in matched)
        budget_ok = (it.get("budget") is None) or (float(it["budget"]) >= floor)
        contact_ok = bool((it.get("public_contact") or {}).get("phone"))
        obs = dt.datetime.fromisoformat(it["observed_at"]) if it.get("observed_at") else now()
        if obs.tzinfo: obs = obs.replace(tzinfo=None)
        fresh = max(0.0, 1 - (now() - obs).days / max(1, ttl_days))
        score = round(w.get("weight", 0.5) * 0.5 + fresh * 0.1 + (0.2 if budget_ok else 0) + (0.1 if contact_ok else 0) + 0.35 * min(1, len(matched) / 2), 3)
        sid = new_id()
        with tx() as s:
            s.execute(T.signal.insert().values(id=sid, tenant_id=tenant_id, source=it.get("source"), stage=stage,
                project_name=it.get("project_name"), company_id=cid, budget=it.get("budget"),
                deadline=dt.date.fromisoformat(it["deadline"]) if it.get("deadline") else None,
                public_contact=it.get("public_contact") or {}, evidence_urls=it.get("evidence_urls") or [],
                raw_text=it.get("raw_text"), raw_hash=hashlib.sha256((it.get("raw_text") or "").encode()).hexdigest(),
                observed_at=obs, ttl_at=ttl_at, status="matched", dedup_key=dedup))
            events.publish(s, "SignalObserved", sid, {"signal_id": sid, "source": it.get("source"), "stage": stage, "dedup_key": dedup}, tenant_id)
        queue.enqueue("research", {"signal_id": sid}, tenant_id, idem_key=idem("research", sid))
        created += 1
    return created
