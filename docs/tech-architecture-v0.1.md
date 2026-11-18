# LeadPilot 技术架构评估 v0.1（DDD 战略设计 + 技术选型 + 拆分路线）

日期：2026-11-17 ｜ 上游：product-design-v0.1.md（含 v0.2/v0.3 增量）

---

## 0. 评估结论速览

| 决策点 | 结论 | 一句话理由 |
|---|---|---|
| 架构风格 | **模块化单体(modulith) + 2 类 worker 进程**，DDD 限界上下文=模块边界；微服务是演进结果不是起点 | 2~3 人团队，分布式单体是最贵错误 |
| 语言 | **Python 优先**(FastAPI modulith + Python AI worker)；若组织强制 Java 则 Spring Boot3+Spring Modulith 核心 + Python AI worker 双运行时 | 本产品 60~70% 逻辑是 LLM 编排/评测/采集，Python 生态决定生产率 |
| 数据库 | **PostgreSQL 单实例**：schema-per-context + JSONB + pgvector + RLS 多租户 + 事务 outbox | 一个库覆盖关系/文档/向量/租户隔离/事件源，MVP 不引第二存储 |
| 队列/事件 | **DB 租约任务队列 + 事务 outbox → Redis Streams**；Kafka/RocketMQ 留到拆服务后 | 需要 replay/多消费组时再上日志型 MQ |
| 缓存/限流 | Redis（平台适配器令牌桶、分布式锁、digest 去重） | 钉钉 20 条/分钟等限流是硬约束 |
| 对象存储 | MinIO/OSS（内容素材、证据附件） | 视频/图片不进 DB |
| 搜索 | PG 中文全文(zhparser/jieba+tsvector)；ES/OpenSearch 后置 | 内容库检索规模未到 |
| 分析 | PG 物化视图读模型；ClickHouse/Doris 后置 | 归因看板先 CQRS 读模型 |
| LLM 网关 | 统一网关(LiteLLM 或自研薄层)：路由/重试/**按调用计量成本→成本账本**；默认 DashScope/Qwen | 成本账本是产品卖点，计量必须架构级 |
| LLM 观测/评测 | Langfuse(self-host) trace + 自建 eval runner（回标集回归门禁） | 评测门禁是质量护城河 |
| 编排 | DB 状态机+逐步 checkpoint（MVP）；Temporal 留到跨服务 saga | 验收→计费→补换 saga 出现时再上 |
| 前端 | **Vue3+TS+Vite+Element Plus/Ant Design Vue**（团队 React 强则 React+AntD Pro）；商家侧不做 App，=三栈卡片+H5 兜底页 | 中文 B2B admin 生态 Vue 更厚；商家活在 IM 里 |
| 身份 | OIDC(Keycloak/云 IAM) + RBAC(owner/approver/sales) + tenant_id RLS | generic 子域，买/集成不自研 |
| 拆分时机 | 触发器驱动：独立扩缩/独立故障域/≥2 squad/部署节奏冲突/数据所有权冲突 | 见 §6 |

---

## 1. DDD 战略设计：限界上下文划分

### 1.1 上下文清单与分类
| # | 限界上下文 | 类型 | 职责 | 核心聚合 |
|---|---|---|---|---|
| BC1 | 租户与行业配置 Tenant&Pack | supporting(战略资产) | 租户、行业包版本、合格定义合同、办公栈、账号登记、计费条款 | Tenant, IndustryPackVersion, QualificationContract, AccountBinding |
| BC2 | 信号与企业图谱 Signal&Company | supporting | 连接器采集、实体归一去重、新鲜度 TTL、PII 来源白名单 | Company, Signal, ConnectorPolicy |
| BC3 | 线索判定 Qualification | **core** | ICP+意向评分、LLM 背调(强制引用)、线索卡产出、rubric 版本 | QualificationJob, LeadCardDraft, RubricVersion |
| BC4 | 线索生命周期与验收 Lifecycle | **core** | 状态机、48h 验收窗、补换队列、交付 digest | Lead, AcceptanceWindow, ReplacementCase |
| BC5 | 计费与成本 Billing&Cost | supporting | 验收事件计量、单线索成本账本、对账单、价格计划 | Meter, CostEntry, Invoice, PricePlan |
| BC6 | 内容工厂 ContentStudio | **core**(inbound) | 选题日历、一源多态、claims 校验、AIGC 标识、审批流 | ContentItem(含 variants/claims), TopicCalendar, ApprovalRequest |
| BC7 | 渠道运营 ChannelOps | supporting | 发布作业(适配器)、平台规则包/限速、承接会话、钩子资产、归因码 | PublishJob, EngagementThread, CaptureAsset, ChannelCode |
| BC8 | 归因与洞察 Attribution | supporting | campaign、归因链、人群包、ROI 读模型、周报 | Campaign, AttributionLink, AudiencePack, ReportSnapshot |
| BC9 | 证据库 Evidence | supporting(信任关键) | 审计战果、授权、宣称引用源 | EvidenceRecord, Authorization |
| BC10 | 合规门禁 Compliance | supporting(横切) | 四道门策略版本、GateDecision、审计 sink | PolicyVersion, GateDecision, AuditRecord |
| BC11 | 反馈与评测 Feedback&Eval | supporting(横切) | 回标→eval case、rubric/选题调优提案、回归门禁、shadow/canary | EvalCase, EvalRun, TuningProposal, Rollout |
| G1 | 身份与访问 Identity | generic | OIDC/RBAC/租户隔离 | 集成 Keycloak/云 IAM |
| G2 | 外部适配器 Adapters | generic(ACL) | 企微/飞书/钉钉、飞鱼/聚光、企查查/天眼查、social-auto-upload/蚁小二、公众号 API | 每外部系统一个 ACL，归属使用方上下文 |

### 1.2 上下文映射（Context Map）
```
BC2 Signal ──(SignalObserved, customer/supplier)──> BC3 Qualification
BC3 ──(LeadCardProduced, published language)──> BC4 Lifecycle
BC4 ──(LeadAccepted/Invalidated/DealClosed, event-carried state)──> BC5 Billing
BC4 ──(labels)──> BC11 Feedback ──(TuningProposal+门禁)──> BC3/BC6
BC4 ──(DealClosed+授权)──> BC9 Evidence ──(conformist: claims 必须引用)──> BC6
BC6 ──(同步 GateCheck + 人审 ApprovalRequest)──> BC10 Compliance
BC6 ──(ContentApproved)──> BC7 ChannelOps ──(ContentPublished/LeadCaptured)──> BC4/BC8
BC7 ──(互动/留资事件)──> BC8 Attribution (CQRS 投影)
BC4/BC5/BC7 ──(审计事件)──> BC10 (audit sink)
BC1 ──(配置快照 OHS)──> 所有上下文
G2 adapters 以 ACL 挂在 BC2/BC7/BC5 边缘，翻译外部模型，不污染领域
```
关系模式说明：BC3→BC4 用 published language（LeadCard DTO 版本化）；BC9→BC6 是 conformist（内容侧服从证据侧模型，杜绝编造）；BC10 提供 OHS 同步策略校验 + 异步审计 sink；BC8 纯下游投影，不反向写核心。

### 1.3 关键聚合不变量（invariants）
- **Lead**：状态转移合法表；每 lead 至多一个计费事件；验收窗 48h 超时自动策略（默认 accepted? 不——默认进入提醒+人工裁决，合同定义）；invalid 必须带理由且触发补换。
- **ContentItem**：无 ApprovalApproved + AIGC 标识 + claims 全引用 → 不可进入 Published；claims 引用必须存在于 BC9 且授权有效。
- **Invoice**：只由 LeadAccepted 事件计量；补换线索不重复计费；幂等键=lead_id+event_id。
- **IndustryPackVersion**：版本化+rollout 状态(shadow/canary/full)；未过 BC11 门禁不可 full。
- **GateDecision**：策略版本+输入哈希+结果+人审 id，全留痕。

### 1.4 领域事件清单（v1）
SignalObserved, CompanyResolved, LeadCardProduced, LeadDelivered, LeadAccepted,
LeadInvalidated, LeadReplaced, OpportunityReported, DealClosed, EvidenceAudited,
TopicProposed, ContentDrafted, GateChecked, ContentApproved, ContentPublished,
EngagementIntentDetected, LeadCaptured, CostRecorded, InvoiceIssued,
EvalRunCompleted, TuningProposed, RolloutChanged, AuditRecorded.
事件信封：event_id, tenant_id, aggregate_id, version, occurred_at, payload, idempotency_key；outbox 同事务写入。

---

## 2. 物理架构：MVP 三进程 + 一库

```
[Console SPA(Vue3)] ─HTTP─> [leadpilot-api (modulith)]
                              │  BC1/BC4/BC5/BC6/BC8/BC9/BC10 模块
                              │  BFF + 审批队列 + 看板读模型
                              │  outbox dispatcher ──> Redis Streams
                              │  webhook ingress(飞鱼/聚光/三栈回调)
                              ├──jobs──> [leadpilot-ai-worker (Python)]
                              │            BC2 采集/BC3 背调评分/BC6 生成/BC11 评测
                              │            逐步 checkpoint + 租约续跑 + 幂等
                              └──jobs──> [leadpilot-channel-worker]
                                           BC7 发布/推送/承接发送；令牌桶限速；
                                           适配器故障隔离(封号/限流不拖垮核心)
[PostgreSQL] schema: tenant/ signal/ lead/ billing/ content/ channel/ attrib/ evidence/ compliance/ eval
           + outbox + job_queue(租约) + RLS(tenant_id)
[Redis] streams/cache/locks/rate-limit   [MinIO/OSS] 素材   [Langfuse] LLM trace
[LLM Gateway] 路由/重试/成本计量 → billing.CostEntry
```
- **为什么 worker 现在就拆进程**：AI 任务长运行、可重试、LLM 并发扩缩与 API 不同；渠道适配器有外部故障域（限流/封号/平台宕机）。这是 MVP 唯一 justified 的拆分。
- **为什么其余不拆**：BC4/BC5/BC10 强事务耦合（验收=计费=门禁同事务），拆服务=自造 saga；团队<5 人无独立所有权需求。
- 模块边界强制：Python 用 import-linter 契约（context 间只许经 events/接口 DTO）；Java 用 Spring Modulith 验证+事件发布注册表。
- 多租户：tenant_id 全表 + PG RLS；适配器凭据 per-tenant 加密存储；禁止跨租户群/机器人。

---

## 3. 数据库评估

| 候选 | 评估 | 结论 |
|---|---|---|
| **PostgreSQL 16+** | JSONB(线索卡证据/行业包)、pgvector(企业/内容去重与选题相似)、RLS(租户隔离)、事务 outbox、LISTEN/NOTIFY、物化视图读模型 | **选它**，MVP 唯一 OLTP |
| MySQL 8 | 团队若只有 MySQL 运维经验可用；但向量/RLS/全文需外置组件，MVP 组件数上升 | 备选(组织标准时) |
| MongoDB | 线索卡文档性诱人，但验收/计费强事务+跨聚合查询弱 | 不选 |
| 向量库(Milvus/Qdrant) | pgvector 百万级足够；独立向量库=第二存储运维 | 后置 |
| ClickHouse/Doris | 归因明细量大后(>千万事件/月)上；MVP 物化视图 | 后置 |
| ES/OpenSearch | 中文内容检索规模到(>百万内容项/复杂聚合)再上；MVP zhparser/jieba+tsvector | 后置 |
存储细则：证据附件/视频素材→OSS；LLM 原始响应→OSS+DB 摘要引用；审计日志→DB 热 90 天+OSS 冷归档；成本计量 double-write 禁止，只经 outbox 事件进 billing。

## 4. 中间件评估

| 组件 | MVP | 演进 | 理由 |
|---|---|---|---|
| 任务队列 | PG job_queue 租约(lease+checkpoint+query-before-retry) | Redis Streams 消费组 → Kafka | 长任务幂等续跑是硬需求(背调/生成/发布) |
| 事件总线 | 事务 outbox + dispatcher → Redis Streams | Kafka(重放/多投影) 或 RocketMQ(阿里系运维) | 拆服务前不需要日志型 MQ |
| 缓存/限流/锁 | Redis | 同 | 平台限流(钉钉20/min、发布频控)令牌桶 |
| 调度 | pg_cron / worker 内 scheduler | 同 | digest/采集/周报定时 |
| 工作流 | DB 状态机+checkpoint | Temporal(跨服务 saga: 验收→计费→补换→对账) | MVP 不引重型编排 |
| 对象存储 | MinIO(自host)/OSS(云) | 同 | 素材与证据附件 |
| LLM 网关 | LiteLLM 或薄自研：路由/退避/预算护栏/按调用成本计量 | 同+模型评测路由 | 成本账本架构级 |
| LLM 观测 | Langfuse self-host | 同 | prompt/trace/成本/评测对齐 |
| 观测 | OTel + Prometheus + Grafana + Loki | +Tempo | 全链路 trace 含 LLM span |
| 身份 | Keycloak 或云 IAM(OIDC) | 同 | generic 不自研 |
| CI/CD | 单 repo(modulith+workers+web) + 评测门禁 job + shadow/canary 发布脚本 | 拆服务后 per-service pipeline | 门禁=回归 eval+合规红队 |

## 5. 语言与前端评估

### 5.1 Java vs Python
| 维度 | Python(FastAPI modulith + workers) | Java(Spring Boot3+Modulith) + Python workers |
|---|---|---|
| AI 编排/评测/采集生态 | **决定性优势**(SDK/pydantic/eval/爬虫) | worker 侧同，但核心与 worker 双语言 |
| 强事务核心(验收/计费/门禁) | 足够(SQLAlchemy+显式事务+outbox) | 略优(成熟事务/类型/并发工具) |
| 2~3 人团队运维面 | **1 运行时/1 CI/1 招聘画像** | 2 运行时/契约漂移风险/双 CI |
| 组织 Java 标准/存量中间件 | 违和 | 契合 |
| 结论 | **默认选** | 仅当组织强制 Java 或团队 Java 明显强 |
双运行时时的契约纪律：事件信封+DTO 用 OpenAPI/JSON Schema 单源生成两侧代码；幂等键与状态机表共享迁移仓库；禁止跨语言直连对方 DB schema。

### 5.2 Vue vs React
- 控制台特征：重表格/审批队列/表单/看板/卡片预览 → 两者都胜任，**按团队技能选**。
- 中文 B2B admin 模板与组件生态：Vue3+Element Plus / Ant Design Vue / vben 更厚 → **默认 Vue3+TS+Vite+Pinia+TanStack Query**。
- 团队 React 强 → React18+TS+AntD Pro+Zustand+TanStack Query，等价可行。
- 商家侧：**不做 App/小程序(MVP)**；验收/审批在三栈互动卡片内完成，兜底=响应式 H5 页(同 SPA 或独立轻 H5)。
- 看板图表：ECharts(两栈通用)。

---

## 6. 微服务拆分路线（触发器驱动）

**原则：限界上下文≠微服务。先 1:1 模块:上下文，沿同一条缝后拆。**

| 阶段 | 形态 | 拆分触发器 |
|---|---|---|
| P0/P1 (MVP, ≤3人) | modulith + ai-worker + channel-worker，1 DB(schema-per-context) | 仅故障域/扩缩差异拆 worker |
| P2 (≥10 付费租户 或 ≥2 squad) | 拆 **Signal&Research 服务**(Python, 采集+背调, 独立扩缩/独立数据 schema)；**ContentStudio 服务**(生成+审批 API)；核心保留 Lead Core(BC1/4/5/9/10) | 独立扩缩(LLM 并发 vs API)、部署节奏冲突、所有权≥2 人 |
| P3 (多行业包/多 squad) | ChannelOps 独立服务(适配器故障隔离+平台规则包独立发布)；Attribution 读服务+ClickHouse；事件总线 Kafka；Temporal 管 验收→计费→补换 saga；DB-per-service + CDC(Debezium) 投影 | 数据所有权冲突、重放需求、跨服务长事务 |
拆分纪律：每次拆分必须带 outbox→MQ 迁移方案、幂等键不变、契约测试(pact/schema)、灰度切流；**禁止 distributed monolith**(共享库表/同步链式调用>2 跳)。

## 7. 横切工程纪律
- 幂等：验收/计费/发布/推送全带 idempotency_key；query-before-retry。
- 状态机：Lead/ContentItem/PublishJob/Rollout 显式状态表+转移守卫。
- 策略引擎：四道门规则版本化、硬校验、人审绑定 payload_hash。
- 评测门禁：回标历史回归+合规红队用例；配置/模型/prompt 变更不过门禁不上线。
- 成本：LLM 网关计量→outbox→CostEntry；单线索/单内容成本可审计。
- 租户隔离：RLS+适配器凭据隔离+跨租户查询 lint。
- 可观测：trace 贯穿 API→worker→LLM→适配器；digest/门禁/补换 SLA 告警。

## 8. 风险与对策
| 风险 | 对策 |
|---|---|
| 过早微服务化 | 触发器表+modulith 边界 lint；拆分需 ADR |
| 双语言契约漂移 | schema 单源生成+契约测试+共享迁移仓库 |
| 中文全文检索弱 | zhparser/jieba 预研 spike；不达标的查询走 ES 后置 |
| LLM 成本失控 | 网关预算护栏+per-tenant 配额+成本账本告警 |
| 平台适配器封禁/限流 | channel-worker 隔离+令牌桶+规则包版本+人审门 |
| 租户数据泄露 | RLS+凭据隔离+审计+跨租户 lint |
| 长任务丢失 | 租约+checkpoint+chaos 演练(kill -9 续跑不双计费) |

## 9. 开放决策（需拍板）
1. 团队语言现状：Python 强 or Java 强 or 组织强制？(决定 §5.1)
2. 云 vs 自host：阿里云(RocketMQ/OSS/DashScope 顺) vs 自host(MinIO/Keycloak/Langfuse)？
3. 前端团队技能：Vue or React？
4. 首个垂直行业(影响 BC2 连接器优先级与 BC1 行业包 schema)？

---

## 10. BC9 证据库上下文 深化设计（v0.2 增量，2026-11-17）

### 10.1 评估结论
- **保留为独立限界上下文**（supporting，但信任关键）。理由：多生产者(BC4/BC5/BC8/租户0流水线)、多消费者(BC6 宣称门、销售素材、对外案例页、计费/续费争议举证)、独立生命周期与合规规则(授权/脱敏/留存/撤销)。并入 BC6 会让 lead core 反向耦合内容；并入 BC4 会让内容宣称依赖 lead core。独立=正确缝。
- 成本杠杆比极高：1 个模块、~6 张表、1 个同步校验 API、3~4 个事件；兑现 P3「证据先行」与「战果即广告」，并构成对 11x 式信任崩塌的架构级免疫。

### 10.2 领域模型
聚合：
- **EvidenceRecord**：type ∈ {case_metric, customer_logo, testimonial, report_snapshot, audit_attestation, external_public_source}；status 状态机 draft→submitted→audited→authorized→published→suspended→revoked/expired；tags(行业/平台/指标类)。
- **Authorization**：scope(允许平台/允许具名或匿名/期限)、consent 记录(卡片按钮确认+时间戳+payload_hash；MVP 不做电子签)、revoked_at。
- **AuditAttestation**：auditor、method(可复现查询 id/SQL+参数)、source_snapshot_hash、period、baseline、attested_at。
- **MetricSnapshot**(VO)：value/unit/period/method/baseline/query_ref —— **裸数字不允许成为证据**。
值对象：ClaimRef(content_id, claim_path, evidence_id)、DesensitizationProfile。
不变量：
- 仅 audited+authorized+未过期 的证据可被引用；
- 撤销/过期必须传播：引用中的已发布内容 → remediation 工作流(告警 owner+编辑/替换/下架计划)；
- logo/具名案例必须有有效 Authorization scope；
- 单租户小样本指标对外发布需具名授权或聚合脱敏(k-匿名阈值)；
- 审计必须可复现：query_ref+snapshot_hash 留存，任何人可重跑核对。

### 10.3 工作流（六步）
1 捕获：DealClosed/InvoiceIssued/ReportSnapshot 事件 → 候选证据 draft（指标从 BC8 读模型按 query_ref 抽取，带 provenance）。
2 脱敏：PII 规则（联系人永不出库；公司名按授权；小样本聚合）。
3 审计：人审重跑 query 核对 → AuditAttestation（MVP 审计人=创始人/运营；冲突风险见 10.6）。
4 授权：租户 owner 卡片确认 scope → Authorization。
5 服务：OHS 同步 API `validate_claim(claim)→{evidence_id,status,scope,expiry}` 供 BC6 门禁；销售素材/案例页只读 published+authorized。
6 撤销/过期：EvidenceRevoked/EvidenceExpired → BC6 标记受影响内容 + remediation_task；BC8/销售资产同步撤下；门禁缓存失效。

### 10.4 接口与事件
- 同步：POST /evidence/claims:validate（BC6 发布门调用；缓存 TTL+撤销事件主动失效）。
- 事件：EvidenceSubmitted, EvidenceAudited, EvidenceAuthorized, EvidencePublished, EvidenceRevoked, EvidenceExpired。
- 表：evidence_record, evidence_metric, authorization, audit_attestation, claim_link, remediation_task；附件 OSS+hash；RLS tenant_id。
- 适配器：平台编辑/删除 API 能力矩阵（能自动下架的自动，不能的进人工 remediation）。

### 10.5 MVP 切分
做：evidence_record/authorization/audit_attestation/claim_link + validate API + 撤销标记 + 卡片授权确认。
不做：电子签集成、第三方审计、案例页 CMS（静态生成页代替）、指标自动重算（审计人重跑保存的 query）。
指标：宣称门拒绝率、已发布内容证据有效率=100%、撤销 remediation SLA≤48h、证据新鲜度(过期率)、授权覆盖率。
额外价值：MetricSnapshot 同时作为**计费/续费争议的举证材料**（BC5 争议流程引用 evidence_id）。

### 10.6 风险与对策
| 风险 | 对策 |
|---|---|
| 门禁过严拖慢营销 | 证据类型含 external_public_source(带 URL 的公开行业数据)，不只自有案例 |
| 创始人审自己数字=利益冲突 | 可复现 query+snapshot_hash+留存；PMF 后引入第三方/客户共审；对外明示审计方法 |
| 授权纠纷 | scope 书面化+卡片确认留痕+撤销即传播 |
| 指标漂移 | period+TTL(指标类默认90天)+到期重审计 |
| 小样本泄露 | k-匿名阈值+具名授权二选一 |
| 已发布内容无法自动下架 | 平台能力矩阵+remediation 人工 SLA+门禁禁止再引用 |

---

## 11. 开放决策裁决（§9 四条）——约束重置：零起步、单人（2026-11-17）

**总原则**：单人团队里，组件数≈运维负担≈死亡概率。每个组件必须回答"凌晨三点坏了谁修"。
答案只能是：云托管、按量付费、或进程内/单容器。DDD 边界保留为包边界+事件名（便宜的缝），
重型 DDD 仪式与一切集群级中间件推迟。**缺的自动化用创始人小时补（concierge），不用中间件补。**

### 11.1 决策1 语言 → Python 单语言，无 Java
- FastAPI modulith + 同代码库 worker；双运行时对单人=契约漂移+双 CI+双倍运维，直接排除。
- 复用 afterpilot 已验证模式：PG 租约队列、逐步 checkpoint、query-before-retry、eval 门禁、零构建控制台。
- Java 仅在"未来加入 Java 强手且核心事务复杂度显著上升"时重议（ADR 记录）。

### 11.2 决策2 云 vs 自host → 关键状态托管 + 其余按量/单容器/进程内
| 组件 | P0 裁决 | 理由 |
|---|---|---|
| PostgreSQL | **云 RDS 基础版**(自动备份/恢复) | 单人 bus factor=1，备份是命；~60~150 元/月 |
| 对象存储 | **OSS 按量** | 零运维，几元/月；不自host MinIO |
| LLM | **DashScope/Qwen 按量** + 自研薄网关(路由/退避/预算护栏/llm_call 计量表) | 有现成 key 与生态；成本计量进成本账本 |
| Redis | **P0 不引入** | 队列在 PG；单 worker 进程内令牌桶即可；P1 多渠道/多 worker 时再加单容器 |
| 身份 | **应用内 auth**(密码哈希+角色+tenant_id) | Keycloak 对单人过重的运维面；OIDC 到 P2 再说 |
| LLM 观测 | **llm_call 表**(prompt/response/tokens/cost/trace_id) | Langfuse v3 需 ClickHouse+Redis+S3，单人排除 |
| 队列/事件 | PG job_queue 租约 + outbox + **进程内 dispatcher** | 不引 Redis Streams/Kafka |
| 编排/搜索/分析 | DB 状态机 / PG 全文 / 物化视图 | Temporal/ES/ClickHouse 全推迟 |
| 部署 | 单台 ECS(2c4g) Docker Compose：api + worker（+P1 redis/channel-worker） | ~100~200 元/月；runbook+备份演练进 repo |
P0 基础设施成本估算：**<400 元/月**（ECS+RDS+OSS+DashScope 按量+域名）。

### 11.3 决策3 前端 → P0 不做 SPA
- P0：FastAPI + Jinja2 + HTMX + Alpine（零构建，复用 demo 控制台模式）：审批队列/线索池/验收/看板够用。
- P1+（设计伙伴要体面）：Vue3 + TS + Vite + Element Plus（中文 admin 模板厚）；React 仅当已有肌肉记忆。
- 商家侧 P0：webhook digest + 控制台验收链接；互动卡片 P1；不做 App/小程序。

### 11.4 决策4 首个垂直行业 → reach 优先于信号丰富度
选择标准（按权重）：
1. **两周内能约到 ≥3 个老板/销售负责人**（design partner 可达性，一票优先）；
2. 公开买入信号结构化且充足（招投标/招聘/新注册）；
3. 客单价高 → 单线索 100~300 元定价成立；
4. 销售驱动型中小企业、企微/钉钉存量；
5. B2B 公示联系方式为主、PII 敏感度低。
- **无 reach 信息时的默认**：工业设备/零部件（长三角切片）——招投标+招聘信号结构化、钉钉契合、客单价高。
- **覆盖规则**：任何能在两周内约到 3 个设计伙伴的行业，覆盖默认。
- 单人容量纪律：**一个行业 × 一个区域切片**；信号量以"每天人工能质检完"为上限。

### 11.5 单人重切清单（相对 §2/§4/§6）
| 项 | P0  fate |
|---|---|
| 进程数 | api + worker 两进程（同 repo）；channel 适配器先做 worker 内模块，P1 拆进程 |
| schema-per-context | 保留（只是命名空间，便宜） |
| tenant_id 全表 | 保留；**RLS 推迟到 P1 多租户** |
| import-linter 模块边界 | 保留（便宜的缝） |
| outbox+幂等+状态机 | 保留（钱和信任的底线，不省） |
| 评测门禁 | 保留但小：回标历史回归+合规红队少量用例 |
| 互动卡片/电子签/第三方审计/案例CMS | 推迟（P1/P2） |
| 证据库 BC9 | **P0 必须在内容工厂之前就位**（最小四表+validate API） |
| 多行业/self-serve/重CRM | 推迟 |

### 11.6 单人运营纪律
- 时间分配：~60% 构建 / ~40% 销售+交付；交付缺口用人工补，记入"自动化债务清单"按 ROI 排期。
- bus factor：RDS 自动备份+每周恢复演练；runbook/凭据/部署全进 repo；不引任何"只有我懂"的自host集群。
- 第一个hire触发器：交付小时>15h/周 或 付费租户≥5 → 先招交付/运营（释放创始人构建+销售），不是先招工程师。
- 止损不变：样品→试点<20% 换行业/合格定义；不扩规模。
