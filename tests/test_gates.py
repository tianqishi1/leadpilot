from leadpilot.shared import gates
from leadpilot.contexts.lifecycle import service as lc
from leadpilot.contexts.content import service as cs
def test_mobile_blocked():
    assert gates.check("data", {"source": "mock", "public_contact": {"phone": "13812345678"}})["decision"] == "block"
def test_landline_allowed():
    assert gates.check("data", {"source": "mock", "public_contact": {"phone": "0512-68888888"}})["decision"] == "allow"
def test_source_whitelist():
    assert gates.check("data", {"source": "evil_scraper", "public_contact": {}})["decision"] == "block"
def test_superlative_blocked():
    assert gates.check("publish", {"aigc_label": True, "body": "全网第一", "claims": []})["decision"] == "block"
def test_aigc_missing_blocked():
    assert gates.check("publish", {"aigc_label": False, "body": "ok", "claims": []})["decision"] == "block"
def test_autocontact_blocked():
    assert gates.check("outreach", {"auto_contact": True, "channel": "digest"})["decision"] == "block"
def test_state_illegal():
    assert "deal" not in lc.TRANS["delivered"]
def test_approve_hash_binding(tid):
    d = cs.draft(tid)
    assert d["status"] == "pending_approval"
    try:
        cs.approve(d["content_id"], "tampered"); assert False
    except cs.StateIllegal:
        pass
