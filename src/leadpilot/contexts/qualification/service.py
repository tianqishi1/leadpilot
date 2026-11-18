"""线索判定（BC3 core）：LLM 背调强制引用 → 线索卡 draft → outbox。分步 checkpoint。"""
import json, logging
from sqlalchemy import select
from leadpilot.shared import tables as T, queue, events, llm
from leadpilot.shared.db import tx
from leadpilot.shared.ids import new_id, idem
log = logging.getLogger("qualification")
SYSTEM = "你是 B2B 采购意向背调员。只依据给定公开信号推断采购需求/窗口/在位供应商hints/开场白。所有事实必须可回溯到 evidence_urls; 不得编造数字或客户名。输出 JSON。"
def research(job):
    tid = job["tenant_id"]; sid = job["payload"]["signal_id"]; cp = job.get("checkpoint") or {}
    with tx() as s:
        sig = s.execute(select(T.signal).where(T.signal.c.id == sid)).mappings().first()
        comp = s.execute(select(T.company).where(T.company.c.id == sig["company_id"])).mappings().first() if sig else None
    if not sig: return
    sig_d = json.loads(json.dumps(dict(sig), ensure_ascii=False, default=str))
    queue.checkpoint(job["id"], job["lease_owner"], {"step": "signal_loaded"})
    with tx() as s:  # query-before-retry: 已存在同幂等 lead 则跳过
        if s.execute(select(T.lead).where(T.lead.c.tenant_id == tid, T.lead.c.idempotency_key == idem("lead", sid))).first():
            return
    res = llm.complete("research", [{"role": "system", "content": SYSTEM},
        {"role": "user", "signal": sig_d, "content": json.dumps(sig_d, ensure_ascii=False)}],
        tid, job_id=job["id"])
    queue.checkpoint(job["id"], job["lease_owner"], {"step": "research_done"})
    try:
        card = json.loads(res["text"])
    except json.JSONDecodeError:
        card = {"inferred_need": sig["project_name"], "confidence": "low", "parse_error": True}
    card.setdefault("opener", card.get("opening_line") or card.get("opener") or card.get("开场白") or card.get("recommended_opening") or "")
    if not card.get("opener"):
        card["opener"] = f"您好, 看到贵司{sig['project_name']}的公开信号, 想跟您确认下采购/扩编计划, 方便聊两句吗?"
    card.setdefault("inferred_need", card.get("intent_summary") or card.get("summary") or card.get("inferred_need") or sig["project_name"])
    pw = card.get("procurement_window")
    if isinstance(pw, dict): pw = pw.get("signal") or pw.get("note") or ""
    card.setdefault("expected_window", pw or card.get("expected_window") or "")
    if card.get("evidence_urls") and not card.get("evidence"): card["evidence"] = card["evidence_urls"]
    card.setdefault("verification_questions", card.get("qualification_questions") or [])
    conf = card.get("confidence")
    if isinstance(conf, (int, float)):
        conf = "high" if conf >= 0.7 else ("medium" if conf >= 0.4 else "low")
    if isinstance(conf, str) and "_" in conf: conf = "medium"
    card["confidence"] = conf or "medium"
    card["score"] = float(card.get("score") or 0.75)
    card["contact_pending"] = not (card.get("public_contact") or {}).get("phone")
    card["contact_verified"] = False  # 抓取/录入联系均需销售电话核实后才算 verified
    card["contact_source"] = "recruitment_page" if sig["source"] in ("hiring_sales",) else "public_signal"
    card.update({"company": comp["name"] if comp else "", "project": sig["project_name"], "stage": sig["stage"],
                 "public_contact": sig["public_contact"], "evidence": sig["evidence_urls"],
                 "score": float(sig["budget"] is not None and 0.8 or 0.75), "observed_at": str(sig["observed_at"])})
    lid = new_id()
    with tx() as s:
        s.execute(T.lead.insert().values(id=lid, tenant_id=tid, company_id=sig["company_id"], signal_ids=[sid],
            source_type="outbound_signal", intent_tier=3, stage=sig["stage"], score=card.get("score"),
            confidence=card.get("confidence"), card=card, status="draft", idempotency_key=idem("lead", sid)))
        s.execute(T.cost_entry.insert().values(id=new_id(), tenant_id=tid, lead_id=lid, kind="llm",
            amount_rmb=res["cost_rmb"], llm_call_id=res["call_id"], idempotency_key=idem("cost", res["call_id"])))
        events.publish(s, "LeadCardProduced", lid, {"lead_id": lid, "score": card.get("score"), "stage": sig["stage"], "confidence": card.get("confidence")}, tid)
    queue.checkpoint(job["id"], job["lease_owner"], {"step": "lead_drafted", "lead_id": lid})
    return lid
