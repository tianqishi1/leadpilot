"""租户与行业配置（BC1）。config_snapshot 为 OHS。"""
import datetime as dt, json
from sqlalchemy import select
from leadpilot.shared import tables as T
from leadpilot.shared.db import tx
from leadpilot.shared.ids import new_id
def config_snapshot(tenant_id):
    with tx() as s:
        r = s.execute(select(T.pack_version).where(T.pack_version.c.tenant_id == tenant_id,
            T.pack_version.c.rollout.in_(["full", "canary"])).order_by(T.pack_version.c.version.desc())).mappings().first()
        if not r:
            r = s.execute(select(T.pack_version).where(T.pack_version.c.tenant_id == tenant_id)
                .order_by(T.pack_version.c.version.desc())).mappings().first()
        cat = s.execute(select(T.catalog_item).where(T.catalog_item.c.tenant_id == tenant_id,
            T.catalog_item.c.active == True)).mappings().all()
    return {"pack": dict(r) if r else None, "catalog": [dict(c) for c in cat]}
def tenant_by_slug(slug):
    with tx() as s:
        r = s.execute(select(T.tenant).where(T.tenant.c.slug == slug)).mappings().first()
    return dict(r) if r else None
def all_tenants():
    with tx() as s:
        return [dict(r) for r in s.execute(select(T.tenant).where(T.tenant.c.status == "active")).mappings().all()]
PACK_SPEC = {
  "pack_key": "yangtze_equipment_v1",
  "region": ["江苏", "浙江", "上海"],
  "categories": ["通用设备", "零部件", "自动化", "环保设备", "电气"],
  "signals": [
    {"source": "js_eia", "stage": "pre_bid", "weight": 0.9, "ttl_days": 180},
    {"source": "tzxm", "stage": "pre_bid", "weight": 0.85, "ttl_days": 180},
    {"source": "land_market", "stage": "pre_bid", "weight": 0.7, "ttl_days": 270},
    {"source": "ccgp", "stage": "bid", "weight": 1.0, "ttl_days": 30},
    {"source": "ggzy", "stage": "bid", "weight": 1.0, "ttl_days": 30},
    {"source": "award", "stage": "post_bid", "weight": 0.4, "ttl_days": 365}],
  "rubric": {"catalog_match": 0.35, "budget": 0.2, "stage_timing": 0.25, "contact": 0.1, "freshness": 0.1, "threshold": 0.7},
  "qualified_definition": "区域切片内制造业主体可核验;信号TTL内;目录匹配置信>=阈值;预算>=地板价;公告截标>=7天或pre-bid带窗口;依法公开经营性联系;180天不重复;证据>=2",
  "billing": {"unit": "accepted_lead", "price_rmb": 150, "replacement_sla_h": 48},
  "content": {"topics": ["项目信息哪里找", "招标太晚怎么办", "销售跑无效项目", "技改采购预算怎么批"], "voice": "老板算账体"},
  "office_stack": ["dingtalk"]}
MERCHANT_PACK = {
  "pack_key": "own_merchant_v1",
  "region": ["江苏", "浙江", "上海"],
  "categories": ["工业设备卖方", "零部件卖方", "自动化卖方", "环保设备卖方", "机电卖方"],
  "signals": [
    {"source": "hiring_sales", "stage": "merchant_intent", "weight": 0.95, "ttl_days": 90},
    {"source": "new_branch", "stage": "merchant_intent", "weight": 0.9, "ttl_days": 180},
    {"source": "exhibition", "stage": "merchant_intent", "weight": 0.8, "ttl_days": 120},
    {"source": "ads_running", "stage": "merchant_intent", "weight": 0.85, "ttl_days": 60},
    {"source": "new_reg", "stage": "merchant_intent", "weight": 0.7, "ttl_days": 180}],
  "rubric": {"catalog_match": 0.35, "budget": 0.1, "stage_timing": 0.3, "contact": 0.15, "freshness": 0.1, "threshold": 0.7},
  "qualified_definition": "制造类卖方主体可核验;有缺线索/扩销售信号(招销售/新分支/参展/在投广告/新注册);依法公开经营联系;区域切片;180天不重复;证据>=2",
  "billing": {"unit": "accepted_lead", "price_rmb": 0, "replacement_sla_h": 48},
  "content": {"topics": ["设备商怎么找项目线索", "招标信息太晚怎么办", "销售扩编后线索从哪来", "参展名单怎么变成订单"], "voice": "老板算账体"},
  "office_stack": ["dingtalk"]}
MERCHANT_CATALOG = [("工业设备卖方", ["装备", "机床", "数控", "产线", "智能"], 0),
                    ("零部件卖方", ["精密", "机械", "零部件"], 0),
                    ("自动化卖方", ["自动化", "智能", "产线"], 0),
                    ("环保设备卖方", ["环保", "废水", "水处理"], 0),
                    ("机电卖方", ["机电", "电气"], 0)]
CATALOG = [("数控机床", ["数控", "机床", "产线", "加工"], 50000),
           ("装配线", ["装配", "产线", "组装"], 80000),
           ("检测设备", ["检测", "质检", "试验"], 30000),
           ("环保设备", ["废水", "环保", "水处理", "废气"], 40000)]
def seed():
    from leadpilot.shared import gates
    gates.seed_policies()
    with tx() as s:
        row = s.execute(select(T.tenant).where(T.tenant.c.slug == "own")).mappings().first()
        if row:
            tid = row["id"]
        else:
            tid = new_id()
            s.execute(T.tenant.insert().values(id=tid, name="LeadPilot 自用(租户0)", slug="own", office_stack=["dingtalk"]))
            s.execute(T.pack_version.insert().values(id=new_id(), tenant_id=tid, pack_key=PACK_SPEC["pack_key"],
                version=1, spec=PACK_SPEC, rollout="full"))
        for cat, kws, floor in CATALOG:
            if not s.execute(select(T.catalog_item).where(T.catalog_item.c.tenant_id == tid,
                    T.catalog_item.c.category == cat)).first():
                s.execute(T.catalog_item.insert().values(id=new_id(), tenant_id=tid, category=cat, keywords=kws, budget_floor=floor))
    # 租户0 = 自用获"商家"线索(merchant pack v2); merchant-demo = 商家用法示例(equipment pack)
    with tx() as s:
        if not s.execute(select(T.pack_version).where(T.pack_version.c.tenant_id == tid,
                T.pack_version.c.pack_key == "own_merchant_v1")).first():
            s.execute(T.pack_version.insert().values(id=new_id(), tenant_id=tid, pack_key="own_merchant_v1",
                version=2, spec=MERCHANT_PACK, rollout="full"))
        for cat, kws, floor in MERCHANT_CATALOG:
            if not s.execute(select(T.catalog_item).where(T.catalog_item.c.tenant_id == tid,
                    T.catalog_item.c.category == cat)).first():
                s.execute(T.catalog_item.insert().values(id=new_id(), tenant_id=tid, category=cat, keywords=kws, budget_floor=floor))
        md = s.execute(select(T.tenant).where(T.tenant.c.slug == "merchant-demo")).mappings().first()
        if not md:
            mdid = new_id()
            s.execute(T.tenant.insert().values(id=mdid, name="商家示例(设备商卖设备)", slug="merchant-demo", office_stack=["dingtalk"]))
            s.execute(T.pack_version.insert().values(id=new_id(), tenant_id=mdid, pack_key=PACK_SPEC["pack_key"], version=1, spec=PACK_SPEC, rollout="full"))
            for cat, kws, floor in CATALOG:
                s.execute(T.catalog_item.insert().values(id=new_id(), tenant_id=mdid, category=cat, keywords=kws, budget_floor=floor))
    from leadpilot.contexts.evidence import service as ev
    with tx() as s:
        has_ev = s.execute(select(T.evidence_record).where(T.evidence_record.c.tenant_id == tid)).first()
    if not has_ev:
        ev.seed_demo_evidence(tid)

def get_channel_config(tid):
    with tx() as s:
        r = s.execute(select(T.tenant).where(T.tenant.c.id == tid)).mappings().first()
    return (r["channel_config"] or {}) if r else {}
def set_channel_config(tid, webhook, secret):
    with tx() as s:
        s.execute(T.tenant.update().where(T.tenant.c.id == tid).values(channel_config={"dingtalk_webhook": webhook, "dingtalk_secret": secret}))
