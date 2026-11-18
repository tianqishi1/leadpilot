"""渠道适配器（BC7）：钉钉 digest 限流+签名+重试+console 兜底；触达门硬禁自动联系。"""
import time, hmac, hashlib, base64, urllib.parse, logging, datetime as dt
import httpx
from leadpilot.shared import gates, ratelimit
from leadpilot.shared.ids import env
from leadpilot.contexts.tenant import service as _tenant
log = logging.getLogger("channel")
def _sign(secret, ts):
    s = f"{ts}\n{secret}"
    h = hmac.new(secret.encode(), s.encode(), digestmod=hashlib.sha256).digest()
    return urllib.parse.quote_plus(base64.b64encode(h))
def send_digest(tid, leads, idem_key):
    g = gates.check("outreach", {"auto_contact": False, "channel": "digest"}, tid)
    if g["decision"] != "allow": raise RuntimeError(f"outreach gate: {g['reasons']}")
    ratelimit.BUCKETS["dingtalk"].take(1)
    from leadpilot.shared import labels
    all_demo = all(labels.is_demo(l["card"]) for l in leads)
    lines = [f"### LeadPilot 线索日报 {dt.date.today()}" + ("（示例数据, 勿拨打）" if all_demo else ""), ""]
    for l in leads:
        c = l["card"]
        contact = c.get("public_contact") or {}
        lines.append(f"- **{c.get('company','')}**｜{c.get('project','')}　{labels.demo_tag(c)}")
        lines.append(f"  阶段: {labels.stage_label(c.get('stage') or l.get('stage'))}｜匹配度: {labels.score_pct(l.get('score'))}｜置信: {labels.conf_label(c.get('confidence'))}")
        if contact.get("phone"):
            lines.append(f"  联系(待核实): {contact.get('name','')} {contact['phone']}")
        else:
            lines.append("  联系: 待补充(官网/工商/人工)")
        opener = c.get("opener") or c.get("opening_line") or ""
        if opener:
            lines.append(f"  建议开场: {opener[:60]}…")
        lines.append(f"  [点击验收(48小时内)](http://127.0.0.1:8000/leads)")
        lines.append("")
    text = "\n".join(lines)
    cfg = _tenant.get_channel_config(tid)
    webhook = cfg.get("dingtalk_webhook") or env("DINGTALK_WEBHOOK")
    secret = cfg.get("dingtalk_secret") or env("DINGTALK_SECRET")
    if not webhook:
        log.info("no dingtalk webhook -> console 兜底 digest %d leads", len(leads))
        return {"channel": "console", "leads": len(leads), "idem": idem_key}
    last = None
    for attempt in range(3):
        ts = str(round(time.time() * 1000))
        url = webhook + (f"&timestamp={ts}&sign={_sign(secret, ts)}" if secret else "")
        try:
            r = httpx.post(url, json={"msgtype": "markdown", "markdown": {"title": "LeadPilot 线索日报", "text": text}}, timeout=10)
            if r.status_code == 200 and r.json().get("errcode") == 0:
                return {"channel": "dingtalk", "leads": len(leads), "idem": idem_key}
            last = RuntimeError(f"dingtalk {r.status_code} {r.text[:100]}")
        except httpx.HTTPError as e:
            last = e
        time.sleep(min(20, 2 ** attempt))
    raise last
def publish_content(tid, content):
    g = gates.check("outreach", {"auto_contact": False, "channel": "card"}, tid)
    if g["decision"] != "allow": raise RuntimeError(f"outreach gate: {g['reasons']}")
    ratelimit.BUCKETS["publish_default"].take(1)
    return {"url": f"local://preview/{content['id']}", "adapter": "mock_local"}

def test_send(tid):
    from leadpilot.shared import gates, ratelimit
    g = gates.check("outreach", {"auto_contact": False, "channel": "digest"}, tid)
    if g["decision"] != "allow": raise RuntimeError(f"outreach gate: {g['reasons']}")
    cfg = _tenant.get_channel_config(tid)
    webhook = cfg.get("dingtalk_webhook") or env("DINGTALK_WEBHOOK")
    secret = cfg.get("dingtalk_secret") or env("DINGTALK_SECRET")
    if not webhook: return {"channel": "console", "ok": True, "note": "未配置 webhook, 控制台兜底"}
    ratelimit.BUCKETS["dingtalk"].take(1)
    ts = str(round(time.time() * 1000))
    url = webhook + (f"&timestamp={ts}&sign={_sign(secret, ts)}" if secret else "")
    r = httpx.post(url, json={"msgtype": "markdown", "markdown": {"title": "LeadPilot 通道测试", "text": "### LeadPilot 通道测试\n钉钉推送通道配置成功。"}}, timeout=10)
    ok = r.status_code == 200 and r.json().get("errcode") == 0
    return {"channel": "dingtalk", "ok": ok, "resp": r.text[:120]}
