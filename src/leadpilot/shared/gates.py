"""四道硬门禁 + append-only 审计（详细设计 §6/§10）。策略版本化。"""
import hashlib, json, re, datetime as dt
from sqlalchemy import select
from leadpilot.shared import tables as T
from leadpilot.shared.db import tx
from leadpilot.shared.ids import new_id
from leadpilot.shared.phone import valid_landline
SUPERLATIVES = ["最好", "第一", "唯一", "国家级", "顶级", "100%", "绝对", " guaranteed"]
SOURCE_WHITELIST = {"js_eia", "tzxm", "land_market", "ccgp", "ggzy", "award", "company_api", "news", "mock",
                    "hiring_sales", "new_branch", "exhibition", "ads_running", "new_reg"}
CONTACT_KEYS = {"name", "role", "phone", "email"}
MOBILE = re.compile(r"^1[3-9]\d{9}$")
LANDLINE = re.compile(r"^0\d{2,3}-?\d{7,8}$")
def _policy(gate):
    with tx() as s:
        r = s.execute(select(T.gate_policy).where(T.gate_policy.c.gate == gate, T.gate_policy.c.active == True)
            .order_by(T.gate_policy.c.version.desc())).mappings().first()
    return dict(r) if r else {"version": 0, "rules": {}}
def _audit(gate, pv, payload, decision, detail, tenant_id=None, actor="system"):
    h = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    with tx() as s:
        s.execute(T.audit_log.insert().values(id=new_id(), tenant_id=tenant_id, gate=gate, policy_version=pv,
            input_hash=h, decision=decision, actor=actor, detail=detail))
    return h
def check(gate, payload, tenant_id=None, actor="system"):
    pol = _policy(gate); reasons = []
    if gate == "data":
        if payload.get("source") not in SOURCE_WHITELIST: reasons.append("source_not_whitelisted")
        c = payload.get("public_contact") or {}
        if set(c) - CONTACT_KEYS: reasons.append("contact_keys_illegal")
        ph = (c.get("phone") or "").strip()
        if ph and MOBILE.match(ph): reasons.append("personal_mobile_forbidden")
        if ph and not valid_landline(ph): reasons.append("phone_not_public_business_format")
    elif gate == "outreach":
        if payload.get("auto_contact"): reasons.append("auto_contact_forbidden")
        if payload.get("channel") not in {"digest", "console", "card"}: reasons.append("channel_not_allowed")
    elif gate == "claim":
        from leadpilot.contexts.evidence import service as ev
        v = ev.validate_claim(tenant_id, payload)
        if not v["ok"]: reasons.append(v["reason"])
    elif gate == "publish":
        if not payload.get("aigc_label"): reasons.append("aigc_label_missing")
        body = payload.get("body", "")
        if any(w in body for w in SUPERLATIVES): reasons.append("superlative_forbidden")
        from leadpilot.contexts.evidence import service as ev
        for cl in payload.get("claims", []):
            v = ev.validate_claim(tenant_id, cl)
            if not v["ok"]: reasons.append(f"claim_unverified:{cl.get('path')}:{v['reason']}")
    else:
        reasons.append("unknown_gate")
    decision = "allow" if not reasons else "block"
    h = _audit(gate, pol["version"], payload, decision, {"reasons": reasons}, tenant_id, actor)
    return {"decision": decision, "reasons": reasons, "input_hash": h, "policy_version": pol["version"]}
def seed_policies():
    with tx() as s:
        for g in ("data", "outreach", "claim", "publish"):
            if not s.execute(select(T.gate_policy).where(T.gate_policy.c.gate == g)).first():
                s.execute(T.gate_policy.insert().values(id=new_id(), gate=g, version=1, rules={}, active=True))
