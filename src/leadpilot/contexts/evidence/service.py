"""证据库（BC9）：状态机/授权/审计/validate_claim/撤销传播。详细设计 §10。"""
import datetime as dt, hashlib, json
from sqlalchemy import select, update
from leadpilot.shared import tables as T, events
from leadpilot.shared.db import tx, utcnow
from leadpilot.shared.ids import new_id, idem
CACHE = {}; CACHE_V = [0]
def now(): return utcnow()
def _bump(): CACHE_V[0] += 1; CACHE.clear()
def create_draft(tenant_id, type_, metric=None, source_urls=None, tags=None, expires_days=90):
    eid = new_id()
    with tx() as s:
        s.execute(T.evidence_record.insert().values(id=eid, tenant_id=tenant_id, type=type_, status="draft",
            metric=metric, source_urls=source_urls or [], tags=tags or [],
            expires_at=now() + dt.timedelta(days=expires_days) if type_ == "case_metric" else None))
        events.publish(s, "EvidenceSubmitted", eid, {"evidence_id": eid}, tenant_id)
    return eid
def transition(eid, to, actor="system", scope=None, method=None):
    legal = {"draft": ["submitted"], "submitted": ["audited"], "audited": ["authorized"],
             "authorized": ["published"], "published": ["suspended", "revoked", "expired"],
             "suspended": ["published", "revoked"]}
    with tx() as s:
        r = s.execute(select(T.evidence_record).where(T.evidence_record.c.id == eid)).mappings().first()
        if not r or to not in legal.get(r["status"], []):
            raise ValueError(f"illegal evidence transition {r['status'] if r else None}->{to}")
        s.execute(update(T.evidence_record).where(T.evidence_record.c.id == eid).values(status=to))
        if to == "audited":
            s.execute(T.audit_attestation.insert().values(id=new_id(), evidence_id=eid, auditor=actor, method=method or "manual"))
        if to == "authorized":
            h = hashlib.sha256(json.dumps(scope or {}, sort_keys=True).encode()).hexdigest()
            s.execute(T.authorization.insert().values(id=new_id(), evidence_id=eid, scope=scope or {"platforms": ["all"], "named": False},
                consent_hash=h, consent_at=now()))
        events.publish(s, f"Evidence{to.capitalize()}", eid, {"evidence_id": eid}, r["tenant_id"])
    _bump()
    return eid
def revoke(eid, actor="owner"):
    with tx() as s:
        r = s.execute(select(T.evidence_record).where(T.evidence_record.c.id == eid)).mappings().first()
        if not r: raise ValueError("no evidence")
        s.execute(update(T.authorization).where(T.authorization.c.evidence_id == eid,
            T.authorization.c.revoked_at.is_(None)).values(revoked_at=now()))
        s.execute(update(T.evidence_record).where(T.evidence_record.c.id == eid).values(status="revoked"))
        events.publish(s, "EvidenceRevoked", eid, {"evidence_id": eid, "reason": "authorization_revoked"}, r["tenant_id"])
    _bump()
def validate_claim(tenant_id, claim):
    eid = claim.get("evidence_id")
    if not eid: return {"ok": False, "reason": "no_evidence_ref"}
    ck = (tenant_id, eid, CACHE_V[0])
    if ck in CACHE: return CACHE[ck]
    with tx() as s:
        r = s.execute(select(T.evidence_record).where(T.evidence_record.c.id == eid,
            T.evidence_record.c.tenant_id == tenant_id)).mappings().first()
        if not r:
            v = {"ok": False, "reason": "evidence_not_found"}
        elif r["status"] not in ("published", "authorized"):
            v = {"ok": False, "reason": f"status_{r['status']}"}
        elif r["expires_at"] and r["expires_at"] < now():
            v = {"ok": False, "reason": "expired"}
        else:
            a = s.execute(select(T.authorization).where(T.authorization.c.evidence_id == eid,
                T.authorization.c.revoked_at.is_(None))).mappings().first()
            v = {"ok": True, "reason": "", "expiry": str(r["expires_at"])} if a else {"ok": False, "reason": "no_authorization"}
    CACHE[ck] = v
    return v
def on_revoked(payload, event):
    eid = payload["evidence_id"]; tid = event["tenant_id"]
    with tx() as s:
        links = s.execute(select(T.claim_link).where(T.claim_link.c.evidence_id == eid)).mappings().all()
        for l in links:
            c = s.execute(select(T.content_item).where(T.content_item.c.id == l["content_id"])).mappings().first()
            if not c: continue
            if c["status"] == "published":
                s.execute(update(T.content_item).where(T.content_item.c.id == c["id"]).values(status="remediation"))
                s.execute(T.remediation_task.insert().values(id=new_id(), tenant_id=tid, content_id=c["id"],
                    evidence_id=eid, reason="evidence_revoked", due_at=now() + dt.timedelta(hours=48),
                    plan={"action": "edit_or_takedown", "platform_capability": "manual_P0"}))
            elif c["status"] in ("approved", "pending_approval", "draft"):
                s.execute(update(T.content_item).where(T.content_item.c.id == c["id"]).values(status="blocked"))
    _bump()
def seed_demo_evidence(tid):
    e1 = create_draft(tid, "external_public_source", source_urls=["https://www.ccgp.gov.cn/public-example"], tags=["行业", "公开"])
    transition(e1, "submitted"); transition(e1, "audited", method="url_recheck"); transition(e1, "authorized", scope={"platforms": ["all"], "named": False}); transition(e1, "published")
    e2 = create_draft(tid, "case_metric", metric={"value": 150, "unit": "元/合格线索", "period": "2026-10",
        "baseline": "商家广告口径约300元/线索", "query_ref": "sql:cost_per_lead_v1"},
        source_urls=["internal://dashboard/cost_per_lead"], tags=["自用战果"])
    transition(e2, "submitted"); transition(e2, "audited", actor="founder", method="sql:cost_per_lead_v1 重跑+snapshot_hash")
    transition(e2, "authorized", scope={"platforms": ["all"], "named": False}); transition(e2, "published")
    return e1, e2
