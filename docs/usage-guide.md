# LeadPilot 使用说明（P0）

更新：2026-11-18 ｜ 适用：leadpilot 当前骨架

## 1. 启动 / 停止 / 登录
```powershell
cd leadpilot
pip install -r requirements.txt        # 首次
python scripts/dev.py                  # 起 api:8000 + worker（读 .env）
python scripts/stop.py                 # 停止
```
- 浏览器开 **http://127.0.0.1:8000**（注意：不要带星号/中文后缀；错路径会自动跳登录）。
- 登录密码 = `.env` 的 `ADMIN_PASSWORD`（默认 dev-admin-password）。
- 日志：var/api.log、var/worker.log。

## 2. 页面与按钮
| 页面 | 作用 |
|---|---|
| 看板 / | ROI/成本/接受率/补换；**立即采集信号**=跑一次 crawl；**立即推送日报**=跑一次 digest；显示当前信号模式(mock/live) |
| 质检 /qa | 线索卡草稿；核对证据后 **通过→待推送** 或 drop |
| 线索池 /leads | 全状态线索；delivered 行可 **accept / invalid(填理由)**；accepted→contacted→opportunity→deal |
| 内容 /content | 生成草稿→门禁→**approve(绑hash)**；**复制文本/下载.md** 半人工发布 |
| 证据 /evidence | 证据状态机 submit/audit/authorize/publish/revoke；撤销会传播到已发布内容 |
| 录入信号 /intake | **半人工贴真实公开信号**→门禁+背调→线索卡（真实来源入口） |
| 配置 /settings | **钉钉 webhook+secret 直接配置+发送测试消息**；行业包/目录只读 |

按钮说明：采集/推送为**手动立即触发**（平时自动：crawl 每 CRAWL_INTERVAL_MIN、digest 每 DIGEST_INTERVAL_H）。点击后**回到看板并显示提示**，稍候刷新质检/线索池看结果。

## 3. 主流程
信号(mock/录入/招聘live) → crawl 采集+门禁+匹配+评分 → DeepSeek 背调 → 线索卡草稿 → /qa 人工质检 → digest 中文日报推钉钉 → **人工联系**(电话/企微, 用开场白+核实问题; 系统不自动联系) → 48h 验收 accept/invalid → accept=计费+回标+证据候选, invalid=48h 补换 → deal → 证据审计 → 内容工厂引用真实战果 → 人审+AIGC标识 → 半人工发布 → inbound 留资 → 飞轮。

## 4. 配置（.env，改后重启 dev.py）
| 键 | 默认 | 说明 |
|---|---|---|
| SIGNAL_MODE | live | mock=演示fixture / live=真实招聘源(+MockMerchant) |
| MODEL_PROVIDER / OPENAI_BASE_URL / LLM_MODEL | openai / deepseek /v1 / deepseek-flash | 背调模型 |
| DINGTALK_WEBHOOK / SECRET | (也可在配置页改, 优先DB) | 钉钉推送 |
| DIGEST_INTERVAL_H | 4 | 每天 24/4=6 次定时日报 |
| CRAWL_INTERVAL_MIN | 30 | 采集间隔 |
| RECRUIT_QUERIES | 苏州\|销售工程师 | 多城市多关键词用 ; 分隔, 放大供给 |
| RECRUIT_PER_ROUND | 5 | 每轮抓几家公司 |
| LLM_DAILY_BUDGET_RMB | 50 | 背调日预算护栏 |
| ADMIN_PASSWORD / SESSION_SECRET | dev-… | 登录/会话, 生产必改 |
| LIVE_GOV | 0 | 政采live开关(WAF 403, 默认关) |
| HEADLESS | 1 | playwright 渲染层(政采仍403, 保留待用) |

## 5. 真实 vs 示例 / 联系方式
- 标签 **【示例数据】**=mock/占位(example.* URL、公司带"示例"), **勿拨打**；**【真实信号】**=真实公开源/录入。
- 联系标 **待核实**(抓取/录入需电话核实) 或 **待补充**(无公示电话); 抓取电话经真实区号校验, 无效号丢弃。
- 系统**不自动外呼/不自动私信**; 触达由人执行。

## 6. 推送容量
- 钉钉 20 消息/分钟; 每消息≤20 条线索自动分块、逐块交付(重试只补未送)。
- 每天条数 = 当天新增∩质检∩销售承接; 单城单kw 供给几十/天, 扩 RECRUIT_QUERIES 可上百; 建议按销售承接 20~50 条/天/人。

## 7. 验收 / 补换 / 计费 / 证据
- delivered 后 48h 内 accept/invalid; 超窗告警; invalid 必填理由→48h 补换。
- accept=计费事件(每线索至多一次)+训练回标+证据候选; 收入/成本/接受率在看板。
- 证据 revoke → 已发布内容进 remediation(48h), 门禁禁止再引用。

## 8. 内容发布（半人工）
content 生成→宣称/证据门禁+AIGC标识→人审 approve→**复制文本/下载.md**→手动贴小红书/抖音/知乎等。自动直发未接(P1, 需账号+风险确认)。

## 9. 常见问题
| 现象 | 原因/处理 |
|---|---|
| 打不开 / Not Found | 服务没起→dev.py; URL 带星号/中文→用 http://127.0.0.1:8000 ; 错路径现已自动跳登录 |
| {"detail":"login required"} | 未登录; 现在浏览器自动跳 /login 表单(API 才 401) |
| 点按钮跳到 {"job_id":null} | 旧bug: 幂等键固定+返回JSON; 已修=每次点击唯一键+303回看板 |
| 群里没消息 | webhook 未配(配置页填+测试)/无 ready 线索/限流退避; 看 worker.log |
| 抓不到政采/环评 | WAF 403(含headless); LIVE_GOV=0; 用招聘源/录入/聚合API |
| 电话看着假 | 区号校验丢弃无效号→标待补充; 不冒充真实联系 |
| 采集后质检页空 | 去重(同公司+项目不重复)/目录不匹配/worker 仍在背调; 稍候刷新或扩 RECRUIT_QUERIES |

## 10. 命令速查
```powershell
python scripts/dev.py / stop.py
python scripts/run_once.py --job crawl|research|digest|dispatch|cleanup|content|publish|eval [--live]
python scripts/run_evals.py --gate        # 评测门禁(独立DB, 离线mock)
python scripts/drill_backup.py            # 备份恢复演练
python scripts/drill_release.py           # 门禁+chaos
python -m pytest -q
```

## 11. 安全
- 凭据只存 .env(gitignored); 聊天明文给过的 key/secret 建议轮换; .env 勿提交/外发。
- 不绕登录/不爬个人手机/不自动联系; 招聘抓取 polite 限速; 官网 fetch 有 SSRF 私网防护。

## 12. 当前限制（P0）
政采/环评 live 关(WAF); 社媒官方留资/人群包未接; 发布半人工; 联系方式需人工/官网/企查API补; 工商/聚合API 待 key/购买。
