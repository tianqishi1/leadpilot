"""LLM 网关：路由/退避/预算护栏/按调用计量（详细设计 §5.4/§6.3）。mock 离线确定性。"""
import datetime as dt, json, logging, time
import httpx
from sqlalchemy import select, func
from leadpilot.shared import tables as T
from leadpilot.shared.db import tx, utcnow
from leadpilot.shared.ids import new_id, env
log = logging.getLogger("llm")
ROUTES = {"extract": "qwen-plus", "score": "qwen-plus", "intent": "qwen-plus", "research": "qwen-max", "content": "qwen-max"}
RATES = {"qwen-plus": (0.0008, 0.002), "qwen-max": (0.0024, 0.0096),
         "deepseek-chat": (0.0002, 0.0008), "deepseek-reasoner": (0.0004, 0.0016), "deepseek-flash": (0.0001, 0.0004)}  # 元/千token 估算
class BudgetExceeded(Exception): pass
class LLMUnavailable(Exception): pass
def _used_today(tenant_id):
    day = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    with tx() as s:
        v = s.execute(select(func.coalesce(func.sum(T.llm_call.c.cost_rmb), 0)).where(
            T.llm_call.c.tenant_id == tenant_id, T.llm_call.c.occurred_at >= day)).scalar()
    return float(v or 0)
def _mock(purpose, messages):
    txt = json.dumps(messages, ensure_ascii=False, default=str)
    if purpose == "research":
        sig = messages[-1].get("signal", {}) if isinstance(messages[-1], dict) else {}
        card = {"inferred_need": f"{sig.get('project_name','项目')} 相关设备/产线采购窗口",
                "expected_window": "pre-bid 阶段约60~90天进入采购/招标（阶段口径, 非承诺）" if sig.get("stage") == "pre_bid" else "按公告截标时间",
                "incumbent_hint": "未识别",
                "opener": f"看到贵司{sig.get('project_name','项目')}已在{sig.get('source','公示')}公开, 我们整理了同区域类似产线的设备配置与预算区间, 可在招标前给您一份参考…",
                "confidence": "medium"}
        return json.dumps(card, ensure_ascii=False), 300, 200
    if purpose == "content":
        return messages[-1].get("body", ""), 200, 400
    return "{}", 100, 50
def complete(purpose, messages, tenant_id, job_id=None, trace_id=None):
    budget = float(env("LLM_DAILY_BUDGET_RMB", "50"))
    used = _used_today(tenant_id)
    if used >= budget and purpose != "research":
        raise BudgetExceeded(f"tenant {tenant_id} used {used:.2f}/{budget}")
    provider = env("MODEL_PROVIDER", "mock")
    model = env("LLM_MODEL") or ROUTES.get(purpose, "qwen-plus")
    if provider == "mock":
        text, ti, to = _mock(purpose, messages)
        cost = 0.01
    else:
        base = env("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        key = env("DASHSCOPE_API_KEY") or env("OPENAI_API_KEY")
        if not key: raise LLMUnavailable("no api key")
        last = None
        for attempt in range(3):
            try:
                r = httpx.post(f"{base}/chat/completions", timeout=60,
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "messages": messages})
                if r.status_code in (429, 500, 502, 503):
                    last = LLMUnavailable(f"http {r.status_code}")
                    time.sleep(min(30, 2 ** attempt))
                    continue
                r.raise_for_status()
                d = r.json()
                text = d["choices"][0]["message"]["content"]
                u = d.get("usage", {})
                ti, to = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
                ri, ro = RATES.get(model, (0.002, 0.006))
                cost = round(ti / 1000 * ri + to / 1000 * ro, 4)
                break
            except httpx.HTTPError as e:
                last = e; time.sleep(min(30, 2 ** attempt))
        else:
            raise LLMUnavailable(str(last))
    call_id = new_id()
    with tx() as s:
        s.execute(T.llm_call.insert().values(id=call_id, tenant_id=tenant_id, job_id=job_id, trace_id=trace_id,
            model=model if provider != "mock" else "mock", tokens_in=ti, tokens_out=to, cost_rmb=cost, purpose=purpose))
    return {"text": text, "tokens_in": ti, "tokens_out": to, "cost_rmb": cost, "model": model, "call_id": call_id}

