# LeadPilot 行业选择评估 + P0 技术实施方案 v0.1（单人零起步）

日期：2026-11-17 ｜ 上游：product-design-v0.1.md、tech-architecture-v0.1.md(§11 单人裁决)

---

## Part I 行业选择评估

### 1. 评估标准与权重
| 标准 | 权重 | 说明 |
|---|---|---|
| 信号结构化与意向明确度 | 25% | 公开信号是否带预算/期限/公示联系方式，LLM 判定歧义低 |
| 客单价→单线索定价空间 | 20% | 能否撑 100~300 元/合格线索 |
| 单人可交付性 | 20% | 区域+品类切片后信号量=单人每日可质检；判定难度低 |
| 在位者缝隙 | 15% | 现有玩家卖什么、没卖什么 |
| PII/合规 | 10% | 联系方式是否依法公开的经营性联系 |
| 内容/GEO 可行性 | 10% | 买家痛点是否可搜索、可内容化 |

### 2. 候选矩阵（1~5 分）
| 候选 | 信号 | 客单 | 单人 | 缝隙 | 合规 | 内容 | 加权 | 结论 |
|---|---|---|---|---|---|---|---|---|
| **A 工业设备/零部件·制造业采购（长三角切片）** | 5 | 5 | 4 | 4 | 4 | 4 | **4.45** | **首选** |
| B 政采商业服务(物业/保洁/安保/餐饮供应/办公) | 5 | 3 | 4 | 3 | 4 | 3 | 3.85 | 备选/第二行业包 |
| C 企业服务(代记账/知识产权/认证) | 4 | 2 | 2 | 2 | 3 | 3 | 2.60 | 不选 |
| D 医疗器械/医药 | 4 | 5 | 2 | 2 | 3 | 2 | 3.05 | 不选(资质/关系/合规否决) |
| E 建筑/工程 | 4 | 5 | 1 | 2 | 3 | 2 | 2.75 | 不选(周期/关系/灰产否决) |
| F 外贸出海(wedge B) | 4 | 4 | 3 | 3 | 4 | 3 | 3.55 | 保留为换道选项(需外贸know-how) |

### 3. 首选 A 的理由与 alpha
- **信号链完整且依法公开**：环评公众参与公示(省生态环境厅/公示平台, 含建设单位+项目内容+联系方式) → 投资项目备案/核准公示(省投资项目在线审批监管平台) → 土地出让公告(自然资源/土地市场网) → 招标预告/公告(政府采购网/公共资源交易平台, 含预算+期限+采购人联系方式) → 中标公告(竞争情报/二期信号)。
- **alpha = 时机**：环评/备案阶段比招标公告早 数周~数月。在位者(千里马/剑鱼等)卖"公告 firehose 订阅"(会员费几千~几万/年, 销售自己筛)；我们卖"**阶段标签+目录匹配+背调+话术+按验收计费**"的线索卡。pre-bid 进入=帮商家在招标前建立联系, 这是在位者不包装的价值。
- **客单价**：设备/零部件/技改采购 10万~100万+ → 100~300 元/合格线索成立。
- **单人容量**：长三角(苏浙沪) × 2~3 品类簇(通用设备/零部件/自动化/环保设备/电气, 按设计伙伴目录定) → 每周几十条信号, 单人可质检。
- **合规**：环评/政采公示联系方式属依法公开的经营性联系; 不爬个人手机号; 招聘信号 P0 不做(ToS 灰), 用备案/环评/土地/招标链替代。
- **内容/GEO**：设备商老板痛点可搜索("项目信息哪里找""招标信息太晚""销售跑无效项目") → 知乎/公众号/视频号内容+GEO 可行。
- 数据获取：P0 爬依法公开页(限速+缓存+robots); 覆盖不足时 P2 接千里马 API/剑鱼数据定制(付费)补量, 不自建全网爬虫。

### 4. 合格线索定义（合同模板, 行业包 A）
1 买方为切片区域内制造业/工业主体, 公示登记可核验;
2 信号在 TTL 内(环评/备案≤180天; 预告/公告按期限);
3 采购内容与商家目录匹配(品类/规格 embedding+规则, 置信≥阈值);
4 预算≥商家地板价(未披露则推断规模≥地板);
5 公告阶段截标≥7天, 或 pre-bid 阶段带预期窗口;
6 含依法公开的经营性联系方式且格式校验通过;
7 与同租户近180天已交付线索不重复(公司+项目);
8 证据链接≥2(信号源+登记)。
验收：销售48h内 accepted/invalid+理由; invalid→48h补换; 计费=accepted 事件。

### 5. 行业包 A schema 实例（yaml sketch）
```
pack: yangtze_equipment_v1
region: [江苏, 浙江, 上海]
categories: [通用设备, 零部件, 自动化, 环保设备, 电气]   # 按设计伙伴目录收敛
signals:
  - {source: js_eia, stage: pre_bid, weight: 0.9, ttl_days: 180}
  - {source: tzxm_jiangsu, stage: pre_bid, weight: 0.85, ttl_days: 180}
  - {source: land_market, stage: pre_bid, weight: 0.7, ttl_days: 270}
  - {source: ccgp_js, stage: bid, weight: 1.0, ttl: deadline}
  - {source: ggzy_js, stage: bid, weight: 1.0, ttl: deadline}
  - {source: award, stage: post_bid, weight: 0.4, use: intel_next_phase}
rubric: {catalog_match: 0.35, budget: 0.2, stage_timing: 0.25, contact: 0.1, freshness: 0.1, threshold: 0.7}
qualified_definition: <§4 八条>
billing: {unit: accepted_lead, price_rmb: 150, replacement_sla_h: 48}
content: {topics: [项目信息哪里找, 招标太晚怎么办, 销售跑无效项目, 技改采购预算怎么批], voice: 老板算账体}
office_stack: [dingtalk]
```

---

## Part II P0 技术实施方案（单人 / Python / <400元月）

### 6. 仓库骨架
```
leadpilot/
  pyproject.toml  alembic/  deploy/compose.yml  .env.example
  src/leadpilot/
    shared/        db.py outbox.py queue.py llm_gateway.py gates.py events.py ids.py
    contexts/
      tenant/      models.py service.py packs/yangtze_equipment.yaml
      signal/      connectors/{js_eia,tzxm,land_market,ccgp,ggzy,company_api,news}.py
                   resolve.py models.py
      qualification/ score.py research.py rubric.py models.py
      lifecycle/   state_machine.py acceptance.py replacement.py models.py
      billing/     meter.py cost.py models.py
      content/     topics.py factory.py claims.py models.py
      channel/     dingtalk.py wecom.py feishu.py publish.py capture.py
      evidence/    models.py service.py
      compliance/  policies.py audit.py
      evals/       runner.py cases/
    api/           main.py routes/{console,webhooks,evidence_api}.py templates/*.html
    worker/        main.py jobs/{crawl,research,content,digest}.py
  web/static/      htmx.min.js alpine.min.js app.css
  evals/datasets/  scripts/{dev,stop,run_evals,drill_backup}.py  docs/
```
进程：api + worker（同 repo, compose 两服务）；PG=RDS；OSS；DashScope；无 Redis/Keycloak/Langfuse/Kafka（§11）。

### 7. 核心表 DDL sketch
```
signal(id, tenant_id, source, stage, project_name, company_id, budget, deadline,
       public_contact, evidence_urls jsonb, raw_hash, observed_at, ttl_at, status)
company(id, tenant_id, name, credit_code, region, industry, reg_status, enriched_at)
lead(id, tenant_id, company_id, signal_ids jsonb, stage, intent_tier, score,
     card jsonb, status, delivered_at, acceptance_due_at, idempotency_key)
lead_event(id, lead_id, type, payload jsonb, actor, occurred_at)   -- 状态机审计+计费源
replacement_case(id, lead_id, reason, due_at, replacement_lead_id, status)
cost_entry(id, tenant_id, lead_id|content_id, kind, amount, llm_call_id, occurred_at)
llm_call(id, tenant_id, job_id, model, tokens_in, tokens_out, cost_rmb, trace_id, ts)
content_item(id, tenant_id, topic, platform, body, claims jsonb, aigc_label, status, approval_id)
claim_link(content_id, claim_path, evidence_id)
evidence_record(id, tenant_id, type, status, metric jsonb, period, baseline, query_ref, snapshot_hash)
authorization(id, evidence_id, scope jsonb, consent_hash, consent_at, revoked_at)
audit_attestation(id, evidence_id, auditor, method, attested_at)
job_queue(id, kind, payload jsonb, lease_owner, lease_until, checkpoint jsonb,
          attempts, status, idempotency_key)
outbox(id, event_type, tenant_id, aggregate_id, payload jsonb, dispatched_at)
audit_log(id, tenant_id, gate, policy_version, input_hash, decision, actor, ts)
eval_case / eval_run / industry_pack_version / tenant / channel_code / publish_job ...
```
全表 tenant_id；RLS P1 开启；schema-per-context 命名空间保留。

### 8. 流水线（job 链, 全部租约+checkpoint+幂等）
crawl(定时,限速,缓存,robots) → normalize+resolve(信用代码/名称归一) → dedup(公司+项目)
→ ICP filter(pack 规则+目录 embedding pgvector) → stage/intent score
→ research job(LLM 强制引用: 规格/规模/在位供应商 hints/公开联系) → lead card draft
→ 人工 QA 队列(console /qa) → digest job(钉钉 webhook, 合并≤20条/分钟)
→ 验收(console 链接 P0 / 卡片 P1) → lead_event → outbox → meter/cost/eval/evidence 候选
内容链：topics→factory(一源多态)→claims 校验(evidence validate)→人审→publish(适配器)→capture(归因码)→lead(source=inbound)

### 9. LLM 网关与门禁
- 网关：DashScope；qwen-plus=抽取/评分, qwen-max=背调/内容；per-tenant 日预算护栏；每次调用写 llm_call→cost_entry。
- 门禁 P0：数据门(来源白名单)/宣称门(evidence validate)/发布门(人审+AIGC标识)/触达门(禁自动联系, 只交付)。
- 评测 P0：首批回标 50 例+合规红队 10 例(PII 泄露/编造宣称/自动联系尝试)；rubric/prompt 变更不过门禁不上线。

### 10. 控制台（HTMX 零构建）
/qa 信号与线索草稿质检 ｜ /leads 池+验收/无效按钮 ｜ /content 草稿审批 ｜ /evidence ｜ /dashboard 周 ROI ｜ /settings pack/目录/digest 通道

### 11. 90 周计划（单人）
| 周 | 交付 |
|---|---|
| W1 | 骨架+compose+RDS；连接器 js_eia+tzxm；resolve/dedup；lead card draft；/qa |
| W2 | 租约队列+outbox+research job+LLM 计量；钉钉 digest；/leads 验收；状态机 |
| W3 | evidence 最小四表+validate；内容工厂(知乎+公众号)+门禁；dogfood 每周2篇 |
| W4 | meter+cost+dashboard v0；sample campaign：30 家设备商, 每家送3张真线索卡 |
| W5~8 | 3~5 设计伙伴 Managed；验收SLA+补换；周 ROI 复盘；回标调 rubric；评测门禁 |
| W9~12 | 钉钉互动卡片(Stream)；channel 拆进程(如需)；pack v2(第二品类簇)；按验收计费上线；案例入证据库→内容 |

### 12. 成本与指标
- 基础设施 <400 元/月；企业 API 富化 ~0.1~0.5 元/次(缓存)；LLM ~1~5 元/线索；聚合器 API P2 再买。
- 指标：接受率≥60~70%；线索→商机>商家基线；60天续费≥70%；补换SLA≥95%；合规事故=0；已发布内容证据有效率=100%。
- 止损：样品→试点<20% → 换品类簇/合格定义, 不扩量；QA 超单人容量 → 缩切片, 不加爬虫。

### 13. 行业特有风险
| 风险 | 对策 |
|---|---|
| 公开页反爬 | 限速+缓存+依法公开页优先；P2 付费聚合器 API 补覆盖 |
| 联系方式失效 | 格式校验+交付前复核+invalid 补换 |
| pre-bid 不确定性 | stage+confidence 标签+TTL；合同写明阶段口径 |
| 在位供应商锁定 | research 标记 incumbent hint → 降分或标注 |
| 项目审批季节性 | 信号量周报+切片弹性 |
| 单人 QA 容量 | 切片上限=每日可质检量；自动化债务清单按 ROI 排期 |

---

## 14. Runbook：「跑通第一条线索卡」具体指什么（v0.2 增量）

### 14.1 定义
`python scripts/dev.py` 只是**启动器**：起 DB(本地容器或 dev sqlite)+api(控制台)+worker，跑迁移。
"拿到线索卡" = worker 执行一轮 job 链：crawl→resolve/dedup→ICP filter→score→research(LLM)→lead card draft→入 /qa 人工质检队列。
脚本不"找客户"，它编排流水线；线索卡是流水线的**结构化产出物**，不是魔法。

### 14.2 两种模式（沿用 demo 的 MODEL_PROVIDER=mock 思路）
- **mock/seed（默认，离线）**：fixture 公示样本(脱敏样例公告)+mock LLM → 确定性跑通全链路，用于开发/评测/演示。第一条卡必出。
- **live**：真连接器(江苏环评公示/投资平台备案等依法公开页)+DashScope → 真实信号。当日无匹配信号时产出 0 条属正常。
切换：env `SIGNAL_MODE=mock|live`、`MODEL_PROVIDER=mock|openai(DashScope)`。

### 14.3 一轮 job 链的具体动作（live 示例路径）
1 crawl：GET 公示列表页→解析条目→GET 详情页→抽取{项目名,建设单位,项目内容,公示联系方式,日期,URL}；限速+缓存+robots。
2 resolve/dedup：公司名归一→company 记录(信用代码可选企业API富化)；区域过滤(苏浙沪)；(公司+项目)去重。
3 ICP filter：品类/规格 vs 商家目录(规则+pgvector embedding)；不匹配丢弃。
4 score：stage 权重(pre_bid 环评0.9)+freshness+预算(若披露)→intent score。
5 research：qwen-max 读信号原文+公司公开信息→推断采购需求/规模/预期窗口/在位供应商hints/建议开场白；**强制引用 evidence_urls**。
6 落库：lead.card(jsonb)+status=draft→console /qa 队列。
7 人质检：/qa 看卡+点证据链接核对→approve→status=ready。
8 digest：ready 卡合并→钉钉 webhook(≤20条/分钟)或 console /leads；status=delivered+acceptance_due=+48h。
9 验收：销售 accept/invalid+理由→lead_event→outbox→计费计量/成本/评测回标/证据候选。

### 14.4 示例线索卡（fixture 示例数据，非真实企业）
```
company: 苏州××精密制造有限公司（示例）
project: 年产50万套新能源汽车零部件技改项目（示例）
stage: pre_bid(环评公示) ｜ observed: 2026-11-12 ｜ ttl: 180d
inferred_need: 新建/改造零部件产线 → 数控机床/装配线/检测设备采购窗口
expected_window: 环评后约60~90天进入设备采购/招标（阶段口径, 非承诺）
public_contact: 项目联系 王工 0512-6xxx xxxx（公示原文, 经营性联系）
score: 0.82 ｜ confidence: medium ｜ incumbent_hint: 未识别
opener: 「看到贵司零部件技改项目已在环评公示, 我们整理了同区域类似产线的
         设备配置与预算区间, 可在招标前给您一份参考…」
evidence: [环评公示URL, 企业登记URL]
status: draft →(人质检)→ ready →(digest)→ delivered →(48h)→ accepted/invalid
```

### 14.5 当天你会看到什么
- 终端：dev.py 打印 api:8000 / worker 启动 / 迁移完成；`python scripts/run_once.py --job crawl` 触发一轮。
- 浏览器 http://127.0.0.1:8000/qa：第一张卡+证据链接+approve 按钮。
- 钉钉群（配置 webhook 后）：一条合并 digest 消息含卡摘要+验收链接。
- /leads：状态与 48h 倒计时；/dashboard：成本与接受率。

### 14.6 四个"不是"
- 不是魔法获客：产出是**候选卡**；质量=源+rubric+你的质检；真检验=商家销售验收率。
- 不是个人手机号：仅依法公开的经营性联系(常为座机/邮箱)；触达决策仍靠销售。
- 不是自动触达：系统止于交付；无外呼/自动私信。
- 不是保证产量：公开页更新节奏+切片过滤决定当日产量；0 条正常, 缩切片或加源而非加爬虫强度。

### 14.7 前置条件
Python 3.11+ / PG(docker 或 dev sqlite) / live 模式需 DashScope key+公网访问公开页 / 钉钉 webhook 可选 / OSS 可选(素材)。

---

## 17. 垂直行业设计 mock（自用先获"商家"线索）+ live 校准结论（2026-11-18）

### 17.1 双层 ICP（回应"给商家用之前自己先拿到商家线索"）
- **租户0 own = 自用获商家线索**：pack `own_merchant_v1`。ICP=需要获客的**卖方商家**(工业设备/零部件/自动化/环保/机电制造商)。
  买入信号(商家缺线索/扩销售)：`hiring_sales`(招销售扩编)/`new_branch`(新设分支)/`exhibition`(参展名单)/`ads_running`(在投获客广告)/`new_reg`(新注册制造类)。
  合格定义：制造类卖方主体可核验+有缺线索信号+依法公开经营联系+区域切片+180天不重复+证据>=2。计费价 0(自用 dogfood)。
  mock fixture 4 家商家 prospects(苏州智能装备/杭州环保设备/上海精密机械/宁波机电) → DeepSeek 真实背调 → 线索卡 → 人审 → 真推钉钉。
  开场白=lead-sample-first："看到贵司在招5个销售/新设分公司…送3条同区域采购线索"。
- **merchant-demo = 商家用法示例**：pack `yangtze_equipment_v1`，ICP=该商家的**买方**(工厂技改采购)，信号=环评/备案/招标链。演示"商家接入后拿自己买方线索"。
- **live-demo = 政采口径全国演示租户**(垂直B示例)。
- 连接器策略：`MockMerchantConnector`(商家意向, P0 半人工录入)始终启用；`MockConnector`(买方 fixture)仅 mock 模式；政采/环评 live 仅 `HEADLESS=1 且 LIVE_GOV=1`。

### 17.2 live 校准实测结论（诚实记录）
- 列表页可抓(政采今日26条真实公告)；已修：同域重定向跟随/浏览器UA/urljoin/区域过滤/白名单(+江苏政采)/平台热线 SITE_HOTLINES 防护。
- **详情页 JS 渲染**：纯 HTML 仅站点 chrome；**headless chromium 亦被 WAF 403**(含 warm+referer)。故 P0 不启用政采 live(`LIVE_GOV=0`)，避免假线索。
- 真实 pre-bid/政采详情获取路径：P2 付费聚合 API(千里马/剑鱼) 或 人工/住宅浏览器校准；P0 主路径=mock+半人工商家信号。
- headless 层(shared/headless.py)已就绪：白名单+限速+当日缓存+warm/referer；安装 playwright+chromium(用户授权)。

### 17.3 凭据与安全
- DingTalk webhook+secret、DeepSeek key 存 `.env`(gitignored)，不进 repo/日志。
- 用户在聊天明文提供过凭据 → 建议测试后轮换 DingTalk secret 与 DeepSeek key；`.env` 勿提交/勿外发。
- LLM：MODEL_PROVIDER=openai + OPENAI_BASE_URL=https://api.deepseek.com/v1 + LLM_MODEL=deepseek-flash(实测 /models 200, chat/completions 200)。
