from leadpilot.contexts.signal import connectors as C
def test_bid_title_filter():
    assert C.bid_title_ok("某单位数控机床采购项目公开招标公告")
    assert not C.bid_title_ok("某单位数控机床采购项目中标公告")
    assert not C.bid_title_ok("某单位更正公告")
def test_region_infer():
    html = "<title>苏州某产线采购招标</title><p>采购人:苏州测试制造有限公司 地址:江苏省苏州市 联系:0512-68888888</p>"
    r = C.parse_detail("ccgp", "bid", html, "https://x/1")
    assert r.region == "江苏"
