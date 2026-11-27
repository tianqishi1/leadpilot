# LeadPilot P0 骨架


> **生态**：底座 [agent-base](https://github.com/tianqishi1/agent-base) · 评测 [eval-pipeline](https://github.com/tianqishi1/eval-pipeline) · 技能 [marketing-skills-cn](https://github.com/tianqishi1/marketing-skills-cn)

依据：docs/tech-implementation-detailed-v0.1.md（唯一实现依据）。
单人零起步：Python 模块化单体(api) + worker 两进程；dev 默认 sqlite 零外部依赖；生产 PG(RDS)+compose。

## 快速开始（离线 mock）
```powershell
pip install -r requirements.txt
python scripts/dev.py        # 建库+seed+起 api:8000 与 worker
python scripts/run_once.py --job crawl      # 触发一轮采集→背调→线索卡草稿
python scripts/run_once.py --job digest     # 交付(无钉钉 webhook 时 console 兜底)
# 浏览器 http://127.0.0.1:8000/  登录密码=ADMIN_PASSWORD(默认 dev-admin-password)
python scripts/stop.py
```
接真实模型/信号：`SIGNAL_MODE=live`、`MODEL_PROVIDER=openai`+`DASHSCOPE_API_KEY`。
live 连接器选择器为 v1 待校准（页面改版会被 eval 门禁拦截）。

## 验证
```powershell
python -m pytest -q
python scripts/run_evals.py --gate
python scripts/drill_release.py     # eval 门禁 + chaos 子集
python scripts/drill_backup.py      # 备份恢复演练(sqlite 复制校验 / PG 提示 pg_dump)
```

## 结构
src/leadpilot/shared{db,tables,ids,events,queue,outbox,llm,gates,http,ratelimit}
src/leadpilot/contexts/{tenant,signal,qualification,lifecycle,billing,content,channel,evidence,evals}
src/leadpilot/api（FastAPI+HTMX 控制台） src/leadpilot/worker（job loop）
scripts/{dev,stop,run_once,run_evals,init_db,drill_backup,drill_release,render_diagrams}
deploy/compose.yml（PG+api+worker） tests/（单元/集成/chaos/红队）

## P0 边界（与方案一致）
- 无 Redis/Keycloak/Langfuse/Kafka；队列=PG/sqlite 租约表；LLM 观测=bill.llm_call 表。
- 发布适配器 P0=mock/local 预览；真实 social-auto-upload/官方 API 适配器 P1。
- 互动卡片/企微/飞书/飞鱼/聚光 P1/P2；触达门硬禁自动联系。
- RLS P1；P0 全表 tenant_id + repo 强制参数。
- 迁移 P0=create_all+schema_version；alembic P1 引入（向前兼容纪律不变）。
