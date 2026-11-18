from leadpilot.contexts.signal import connectors as C
def test_parse_list():
    html = '<a href="/p/1">某技改项目环评公示</a><a href="/x">无关链接</a>'
    out = C.parse_list("js_eia", "pre_bid", html, "https://www.js-eia.cn")
    assert len(out) == 1 and out[0]["url"].startswith("https://")
def test_parse_detail():
    html = "<title>年产50万套零部件技改项目环评公示</title><p>建设单位:苏州测试精密制造有限公司 预算: 80 万元 联系: 0512-68888888</p>"
    r = C.parse_detail("js_eia", "pre_bid", html, "https://x/1")
    assert r.company_name == "苏州测试精密制造有限公司"
    assert r.budget == 800000.0
    assert r.public_contact["phone"] == "0512-68888888"
def test_mock_fixtures():
    items = C.MockConnector().fetch()["items"]
    assert len(items) == 7  # 3 buyer + 4 merchant fixtures
