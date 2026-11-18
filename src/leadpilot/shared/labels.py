"""面向人的中文标签（内部枚举不外泄到用户界面/推送）。"""
STAGE_LABEL = {"merchant_intent": "商家意向(缺线索/扩销售)", "pre_bid": "招标前(环评/备案)", "bid": "招标中",
               "post_bid": "招标后(竞争情报)", "intent": "意向"}
STATUS_LABEL = {"draft": "草稿待质检", "ready": "待推送", "delivered": "已交付待验收", "accepted": "已验收",
                "contacted": "已联系", "opportunity": "商机", "deal": "成交", "invalid": "无效待补换",
                "replaced": "已补换", "dropped": "已丢弃", "blocked": "门禁拦截", "remediation": "待整改",
                "pending_approval": "待审批", "approved": "已批准", "published": "已发布",
                "submitted": "已提交", "audited": "已审计", "authorized": "已授权", "revoked": "已撤销", "expired": "已过期"}
CONF_LABEL = {"high": "高", "medium": "中", "low": "低", "low_to_medium": "中低", "medium_to_high": "中高"}
def stage_label(s): return STAGE_LABEL.get(s, s or "")
def status_label(s): return STATUS_LABEL.get(s, s or "")
def conf_label(c): return CONF_LABEL.get(c, "中")
def score_pct(x):
    try: return f"{int(round(float(x) * 100))}%"
    except (TypeError, ValueError): return "—"

def is_demo(card):
    """证据URL为 example.* 占位 或 公司名含"示例" => 演示数据, 非真实企业/联系方式。"""
    comp = (card or {}).get("company", "") or ""
    if "示例" in comp: return True
    for u in (card or {}).get("evidence", []) or []:
        if "example" in (u or ""): return True
    return False
def demo_tag(card): return "【示例数据】" if is_demo(card) else "【真实信号】"
