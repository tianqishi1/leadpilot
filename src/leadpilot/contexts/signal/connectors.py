"""信号连接器（BC2）。mock fixture 离线确定性；live 选择器 v1 待校准（改版会被 eval 拦截）。"""
import datetime as dt, re, os
from urllib.parse import urljoin
from dataclasses import dataclass, field, asdict
from leadpilot.shared import http, headless
from leadpilot.shared.ids import env
from leadpilot.shared.phone import valid_landline, clean_company
from leadpilot.shared.db import utcnow
@dataclass
class RawSignal:
    source: str; stage: str; project_name: str; company_name: str; region: str = ""
    budget: float | None = None; deadline: str | None = None
    public_contact: dict = field(default_factory=dict); evidence_urls: list = field(default_factory=list)
    raw_text: str = ""; observed_at: str = ""
FIXTURES = [
    RawSignal("mock", "pre_bid", "年产50万套新能源汽车零部件技改项目", "苏州示例精密制造有限公司", "江苏",
              None, None, {"name": "王工", "role": "项目联系", "phone": "0512-68888888"},
              ["https://www.js-eia.cn/publicity/example-1", "https://www.ccgp.gov.cn/example-reg-1"],
              "建设单位:苏州示例精密制造有限公司;项目内容:新建零部件产线,购置数控机床与装配线;公示联系:王工 0512-68888888",
              utcnow().isoformat()),
    RawSignal("mock", "bid", "某厂区废水处理设备采购项目", "杭州示例环保科技有限公司", "浙江", 1200000,
              (utcnow() + dt.timedelta(days=20)).date().isoformat(),
              {"name": "李工", "role": "采购人联系", "phone": "0571-87777777"},
              ["https://www.ccgp.gov.cn/example-2", "https://www.ccgp.gov.cn/example-reg-2"],
              "采购内容:废水处理设备一批;预算:120万元;截标:20天后;采购人联系:李工 0571-87777777",
              utcnow().isoformat()),
    RawSignal("mock", "pre_bid", "示例写字楼物业保洁服务外包项目", "上海示例物业管理有限公司", "上海",
              None, None, {"name": "赵经理", "role": "联系", "phone": "021-66666666"},
              ["https://www.js-eia.cn/publicity/example-3"], "物业保洁服务外包, 与设备目录无关",
              utcnow().isoformat()),
]
MERCHANT_FIXTURES = [
    RawSignal("hiring_sales", "merchant_intent", "扩招销售团队(5人)", "苏州示例智能装备有限公司", "江苏",
              None, None, {"name": "周总", "role": "总经理", "phone": "0512-65555555"},
              ["https://example-job.example/sz-zhineng-5sales", "https://www.ccgp.gov.cn/example-reg-sz"],
              "招聘:销售工程师x5; 主营:数控机床/自动化产线; 联系:周总 0512-65555555",
              dt.datetime.now(dt.timezone.utc).isoformat()),
    RawSignal("new_branch", "merchant_intent", "新设杭州分公司", "杭州示例环保设备有限公司", "浙江",
              None, None, {"name": "吴总", "role": "法人", "phone": "0571-86666666"},
              ["https://example-reg.example/hz-huanbao-branch", "https://www.ccgp.gov.cn/example-reg-hz"],
              "新设分支机构:杭州分公司; 主营:废水处理设备; 联系:吴总 0571-86666666",
              dt.datetime.now(dt.timezone.utc).isoformat()),
    RawSignal("exhibition", "merchant_intent", "参展2026华东工业博览会", "上海示例精密机械有限公司", "上海",
              None, None, {"name": "郑总", "role": "销售总监", "phone": "021-57777777"},
              ["https://example-expo.example/2026-east-china-list", "https://www.ccgp.gov.cn/example-reg-sh"],
              "参展商名单:精密机械/零部件; 联系:郑总 021-57777777",
              dt.datetime.now(dt.timezone.utc).isoformat()),
    RawSignal("ads_running", "merchant_intent", "在投搜索广告(获客关键词)", "宁波示例机电设备有限公司", "浙江",
              None, None, {"name": "冯总", "role": "市场负责人", "phone": "0574-88888888"},
              ["https://example-ads.example/nb-jidian-running", "https://www.ccgp.gov.cn/example-reg-nb"],
              "在投广告:关键词'机电设备采购/厂家'; 主营:机电/电气; 联系:冯总 0574-88888888",
              dt.datetime.now(dt.timezone.utc).isoformat()),
]
class MockConnector:
    source = "mock"
    def fetch(self, since=None, cursor=None):
        return {"items": [asdict(x) for x in FIXTURES + MERCHANT_FIXTURES], "next_cursor": None}
def parse_list(source, stage, html, base):
    """选择器 v1：抽取公示条目链接+标题（纯函数, 可单测/可 eval）。"""
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,80})</a>', html):
        href, title = m.group(1), m.group(2).strip()
        if any(k in title for k in ("公示", "公告", "备案", "核准", "招标", "采购")):
            url = href if href.startswith("http") else urljoin(base if base.endswith("/") else base + "/", href)
            out.append({"url": url, "title": title})
    return out
def parse_detail(source, stage, html, url):
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    company = ""
    m = re.search(r"(?:建设单位|采购人|项目单位)[::\s]*([一-龥A-Za-z()（）]{4,40}(?:公司|厂|集团|院))", text)
    if m: company = m.group(1)
    phone = ""
    m = re.search(r"(0\d{2,3}-?\d{7,8})", text)
    if m: phone = m.group(1)
    if phone in SITE_HOTLINES: phone = ""
    budget = None
    m = re.search(r"预算[金额]*[::\s]*([\d.]+)\s*(万元|元)", text)
    if m: budget = float(m.group(1)) * (10000 if m.group(2) == "万元" else 1)
    region = ""
    for prov in ("江苏", "浙江", "上海", "北京", "广东", "山东", "安徽", "福建", "四川", "湖北", "湖南", "河南", "河北", "陕西", "辽宁", "吉林", "黑龙江", "江西", "广西", "云南", "贵州", "山西", "甘肃", "海南", "天津", "重庆", "内蒙古", "新疆", "西藏", "青海", "宁夏"):
        if prov in text:
            region = prov
            break
    title = ""
    m = re.search(r"<title>([^<]+)</title>", html)
    if m: title = m.group(1).strip()
    return RawSignal(source=source, stage=stage, project_name=title or text[:60], company_name=company,
                     region=region, budget=budget, public_contact={"phone": phone} if phone else {},
                     evidence_urls=[url], raw_text=text[:4000],
                     observed_at=utcnow().isoformat())
class JsEiaConnector:
    source = "js_eia"; stage = "pre_bid"; base = "https://www.js-eia.cn"
    def fetch(self, since=None, cursor=None):
        html = headless.render(self.base + "/") if headless.available() else http.fetch(self.source, self.base + "/publicity/")
        items = []
        for e in parse_list(self.source, self.stage, html, self.base)[:10]:
            try:
                d = http.fetch(self.source, e["url"])
                items.append(asdict(parse_detail(self.source, self.stage, d, e["url"])))
            except http.SourceUnavailable:
                continue
        return {"items": items, "next_cursor": None}
class TzxmConnector:
    source = "tzxm"; stage = "pre_bid"; base = "https://new.tzxm.gov.cn"
    def fetch(self, since=None, cursor=None):
        html = http.fetch(self.source, self.base + "/")
        items = []
        for e in parse_list(self.source, self.stage, html, self.base)[:10]:
            try:
                d = http.fetch(self.source, e["url"])
                items.append(asdict(parse_detail(self.source, self.stage, d, e["url"])))
            except http.SourceUnavailable:
                continue
        return {"items": items, "next_cursor": None}
SITE_HOTLINES = ("400-810-1996", "010-63819289")  # 平台热线, 非采购人联系, 禁止入线索
BID_TITLE_KEEP = ("招标", "采购", "询价", "竞争性", "磋商", "谈判")
BID_TITLE_DROP = ("中标", "成交", "更正", "终止", "废标", "结果")
def bid_title_ok(title):
    return any(k in title for k in BID_TITLE_KEEP) and not any(k in title for k in BID_TITLE_DROP)
class CcgpConnector:
    """live v2: 中国政府采购网 招标公告列表(server-rendered, UA 必需)。bid 阶段真实源。"""
    source = "ccgp"; stage = "bid"; base = "https://www.ccgp.gov.cn"
    list_url = "https://www.ccgp.gov.cn/cggg/zygg/"
    def fetch(self, since=None, cursor=None):
        html = http.fetch(self.source, self.list_url)
        items = []
        for e in parse_list(self.source, self.stage, html, self.list_url):
            if not bid_title_ok(e["title"]):
                continue
            try:
                d = headless.render(e["url"], warm=self.list_url) if headless.available() else http.fetch(self.source, e["url"])
                rs = parse_detail(self.source, self.stage, d, e["url"])
                rs.project_name = e["title"]
                items.append(asdict(rs))
            except http.SourceUnavailable:
                continue
            if len(items) >= 8:
                break
        return {"items": items, "next_cursor": None}
class RecruitmentConnector:
    """live 真实源: 职友集(server-rendered) 招聘页 -> 真实公司名+在招销售/扩编信号;
    联系方式优先公司页公示电话, 否则官网富化, 否则标"待补充"。polite 2s/域, 限5公司/轮。"""
    source = "hiring_sales"; stage = "merchant_intent"
    def fetch(self, since=None, cursor=None):
        from urllib.parse import quote
        per_round = int(env("RECRUIT_PER_ROUND", "5"))
        queries = env("RECRUIT_QUERIES", "苏州|销售工程师").split(";")
        hrefs = []
        for q in queries:
            city, kw = (q.split("|") + ["销售工程师"])[:2]
            lu = f"https://www.jobui.com/jobs?jobKw={quote(kw)}&cityKw={quote(city)}"
            try:
                html = http.fetch(self.source, lu)
            except http.SourceUnavailable:
                continue
            hrefs += re.findall(r'href="(/company/\d+/)"', html)
        hrefs = list(dict.fromkeys(hrefs))[:per_round]
        items = []
        for h in hrefs:
            cu = "https://www.jobui.com" + h
            try:
                d = http.fetch(self.source, cu)
            except http.SourceUnavailable:
                continue
            txt = re.sub(r"<[^>]+>", " ", d); txt = re.sub(r"\s+", " ", txt)
            m = re.search(r"<title>([^<]+)</title>", d)
            name = (m.group(1).split("_")[0].split("-")[0].strip() if m else "")
            name = clean_company(name) or clean_company(txt)
            phone = ""
            pm = re.search(r"(0\d{2,3}-?\d{7,8})", d)
            if pm and valid_landline(pm.group(1)): phone = pm.group(1)
            site = re.findall(r'href="(https?://[^"]+)"[^>]*>\s*(?:官网|公司网站|进入官网|官方网站)', d)
            if not phone and site:
                try:
                    od = http.fetch_public(site[0])
                    op = re.search(r"(0\d{2,3}-?\d{7,8})", od)
                    if op and valid_landline(op.group(1)): phone = op.group(1)
                except Exception:
                    pass
            njob = re.search(r"(\d+)\s*个?在招职位", txt)
            items.append(asdict(RawSignal(self.source, self.stage,
                f"在招销售/扩编({njob.group(1) if njob else '多'}职位)", name, "江苏",
                None, None, {"phone": phone} if phone else {},
                [cu, h and "https://www.jobui.com" + h + "jobs/"], txt[:1500],
                dt.datetime.now(dt.timezone.utc).isoformat())))
        return {"items": items, "next_cursor": None}
class MockMerchantConnector(MockConnector):
    """商家意向信号 P0 半人工录入(mock fixture); live 模式下也保留(自用 dogfood)。"""
    def fetch(self, since=None, cursor=None):
        return {"items": [asdict(x) for x in MERCHANT_FIXTURES], "next_cursor": None}
def connectors():
    if env("SIGNAL_MODE", "mock") == "mock":
        return [MockConnector()]
    # 详情页 JS 渲染: HEADLESS=1 且 playwright 可用时用渲染层; 否则 live 返回空(默认 mock), 避免假线索。
    base = [MockMerchantConnector(), RecruitmentConnector()]
    if headless.available() and env("LIVE_GOV", "0") == "1":
        base += [CcgpConnector(), JsEiaConnector()]  # 政采详情 WAF 403 反爬(含 headless), 默认关; P2 付费聚合API 或人工校准后开
    return base
