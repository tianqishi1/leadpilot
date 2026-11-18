"""内容工厂（BC6 core inbound）：选题→一源多态→claims校验→门禁→人审→发布。"""
import hashlib, json, datetime as dt
from sqlalchemy import select, update
from leadpilot.shared import tables as T, gates, events, llm
from leadpilot.shared.db import tx
from leadpilot.shared.ids import new_id, idem
from leadpilot.contexts.tenant import service as tenant
class StateIllegal(Exception): pass
def _hash(body, claims): return hashlib.sha256(json.dumps({"body": body, "claims": claims}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
def draft(tid, topic=None, platform="zhihu"):
    cfg = tenant.config_snapshot(tid)
    topics = ((cfg["pack"] or {}).get("spec") or {}).get("content", {}).get("topics", ["项目信息哪里找"])
    topic = topic or topics[0]
    with tx() as s:
        evs = s.execute(select(T.evidence_record).where(T.evidence_record.c.tenant_id == tid,
            T.evidence_record.c.status == "published")).mappings().all()
    ev = next((e for e in evs if e["type"] == "case_metric"), evs[0] if evs else None)
    claims = []
    if ev and ev["metric"]:
        m = ev["metric"]
        line = f"实测单合格线索成本 {m.get('value')}{m.get('unit','')}（口径:{m.get('period','')}, 基线:{m.get('baseline','')}）。"
        claims = [{"path": "body.cost", "evidence_id": ev["id"], "value": m.get("value")}]
    else:
        line = "本文不含未审计数字。"
    body = f"# {topic}\n\n老板算账体：先算单线索成本，再算销售时间。\n{line}\n方法：公开买入信号(环评/备案/招标)→目录匹配→背调带证据→销售48h验收。\n（AI 生成, 已标识）"
    g = gates.check("publish", {"aigc_label": True, "body": body, "claims": claims}, tid)
    cid = new_id()
    status = "pending_approval" if g["decision"] == "allow" else "blocked"
    with tx() as s:
        s.execute(T.content_item.insert().values(id=cid, tenant_id=tid, topic=topic, platform=platform, body=body,
            claims=claims, aigc_label=True, status=status, payload_hash=_hash(body, claims)))
        for cl in claims:
            s.execute(T.claim_link.insert().values(content_id=cid, claim_path=cl["path"], evidence_id=cl["evidence_id"]))
    return {"content_id": cid, "status": status, "gate": g}
def approve(cid, payload_hash, actor="owner"):
    with tx() as s:
        c = s.execute(select(T.content_item).where(T.content_item.c.id == cid)).mappings().first()
        if not c: raise StateIllegal("no content")
        if c["status"] != "pending_approval": raise StateIllegal(f"approve from {c['status']}")
        if payload_hash != c["payload_hash"]: raise StateIllegal("payload_hash mismatch (审后改被拒)")
        s.execute(update(T.content_item).where(T.content_item.c.id == cid).values(status="approved", approval_id=new_id()))
        events.publish(s, "ContentApproved", cid, {"content_id": cid, "payload_hash": payload_hash}, c["tenant_id"])
def publish(job):
    cid = job["payload"]["content_id"]; tid = job["tenant_id"]
    from leadpilot.contexts.channel import dingtalk
    with tx() as s:
        c = s.execute(select(T.content_item).where(T.content_item.c.id == cid)).mappings().first()
        if not c or c["status"] != "approved": return
        pj = s.execute(select(T.publish_job).where(T.publish_job.c.tenant_id == tid,
            T.publish_job.c.idempotency_key == idem("pub", cid))).mappings().first()
        if pj and pj["status"] == "done": return
        if not pj:
            s.execute(T.publish_job.insert().values(id=new_id(), tenant_id=tid, content_id=cid, adapter="mock_local",
                platform=c["platform"], idempotency_key=idem("pub", cid)))
    receipt = dingtalk.publish_content(tid, c)  # P0=mock/local 预览; 真实适配器 P1
    with tx() as s:
        s.execute(update(T.publish_job).where(T.publish_job.c.tenant_id == tid,
            T.publish_job.c.idempotency_key == idem("pub", cid)).values(status="done", external_url=receipt.get("url")))
        s.execute(update(T.content_item).where(T.content_item.c.id == cid).values(status="published"))
        code = f"lp-{c['platform']}-{cid[:6]}"
        if not s.execute(select(T.channel_code).where(T.channel_code.c.code == code)).first():
            s.execute(T.channel_code.insert().values(id=new_id(), tenant_id=tid, code=code, platform=c["platform"], campaign=c["topic"]))
        events.publish(s, "ContentPublished", cid, {"content_id": cid, "platform": c["platform"],
            "external_url": receipt.get("url"), "channel_code": code}, tid)
def lists(tid):
    with tx() as s:
        rows = [dict(r) for r in s.execute(select(T.content_item).where(T.content_item.c.tenant_id == tid)
            .order_by(T.content_item.c.created_at.desc())).mappings().all()]
        rem = [dict(r) for r in s.execute(select(T.remediation_task).where(T.remediation_task.c.tenant_id == tid,
            T.remediation_task.c.status == "open")).mappings().all()]
    return rows, rem
