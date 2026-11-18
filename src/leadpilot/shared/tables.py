"""24 表 DDL（dialect-neutral：PG schema-per-context / sqlite 平铺）。依据详细设计 §4。"""
import sqlalchemy as sa
from leadpilot.shared.db import meta, sch, utcnow
from leadpilot.shared.ids import new_id
import datetime as dt
def pk(): return sa.Column("id", sa.String(36), primary_key=True, default=new_id)
def tid(): return sa.Column("tenant_id", sa.String(36), nullable=False, index=True)
def ts(n="created_at"): return sa.Column(n, sa.DateTime, default=lambda: utcnow())
J = sa.JSON
# ---- tn ----
tenant = sa.Table("tenant", meta, pk(), sa.Column("name", sa.Text, nullable=False),
    sa.Column("slug", sa.Text, unique=True, nullable=False), sa.Column("mode", sa.Text, default="managed"),
    sa.Column("office_stack", J, default=list), sa.Column("status", sa.Text, default="active"),
    sa.Column("channel_config", J, default=dict), ts(), schema=sch("tn"))
pack_version = sa.Table("industry_pack_version", meta, pk(), tid(), sa.Column("pack_key", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False), sa.Column("spec", J, nullable=False),
    sa.Column("rollout", sa.Text, default="shadow"), sa.Column("eval_run_id", sa.String(36)), ts(),
    sa.UniqueConstraint("tenant_id", "pack_key", "version"), schema=sch("tn"))
catalog_item = sa.Table("catalog_item", meta, pk(), tid(), sa.Column("category", sa.Text, nullable=False),
    sa.Column("keywords", J, default=list), sa.Column("specs", J, default=dict),
    sa.Column("budget_floor", sa.Numeric(12, 2)), sa.Column("active", sa.Boolean, default=True), schema=sch("tn"))
# ---- sig ----
company = sa.Table("company", meta, pk(), tid(), sa.Column("name", sa.Text, nullable=False),
    sa.Column("credit_code", sa.Text), sa.Column("region", sa.Text), sa.Column("industry", sa.Text),
    sa.Column("reg_status", sa.Text), sa.Column("enriched_at", sa.DateTime),
    sa.UniqueConstraint("tenant_id", "name", "credit_code"), schema=sch("sig"))
signal = sa.Table("signal", meta, pk(), tid(), sa.Column("source", sa.Text, nullable=False),
    sa.Column("stage", sa.Text, nullable=False), sa.Column("project_name", sa.Text, nullable=False),
    sa.Column("company_id", sa.String(36)), sa.Column("budget", sa.Numeric(14, 2)), sa.Column("deadline", sa.Date),
    sa.Column("public_contact", J, default=dict), sa.Column("evidence_urls", J, default=list),
    sa.Column("raw_text", sa.Text), sa.Column("raw_hash", sa.Text, nullable=False),
    sa.Column("observed_at", sa.DateTime, nullable=False), sa.Column("ttl_at", sa.DateTime, nullable=False),
    sa.Column("status", sa.Text, default="new"), sa.Column("dedup_key", sa.Text, nullable=False), ts(),
    sa.UniqueConstraint("tenant_id", "dedup_key"), schema=sch("sig"))
sa.Index("idx_signal_ttl", signal.c.tenant_id, signal.c.ttl_at, postgresql_where=signal.c.status == "new")
# ---- ld ----
lead = sa.Table("lead", meta, pk(), tid(), sa.Column("company_id", sa.String(36), nullable=False),
    sa.Column("signal_ids", J, default=list), sa.Column("source_type", sa.Text, nullable=False),
    sa.Column("intent_tier", sa.Integer, default=3), sa.Column("stage", sa.Text), sa.Column("score", sa.Numeric(4, 3)),
    sa.Column("confidence", sa.Text), sa.Column("card", J, nullable=False), sa.Column("status", sa.Text, default="draft"),
    sa.Column("channel_code_id", sa.String(36)), sa.Column("delivered_at", sa.DateTime),
    sa.Column("acceptance_due_at", sa.DateTime), sa.Column("idempotency_key", sa.Text, nullable=False),
    ts(), ts("updated_at"), sa.UniqueConstraint("tenant_id", "idempotency_key"), schema=sch("ld"))
sa.Index("idx_lead_status", lead.c.tenant_id, lead.c.status, lead.c.acceptance_due_at)
lead_event = sa.Table("lead_event", meta, pk(), sa.Column("lead_id", sa.String(36), nullable=False), tid(),
    sa.Column("type", sa.Text, nullable=False), sa.Column("payload", J, default=dict), sa.Column("actor", sa.Text),
    sa.Column("idempotency_key", sa.Text, nullable=False), ts("occurred_at"),
    sa.UniqueConstraint("lead_id", "type", "idempotency_key"), schema=sch("ld"))
replacement_case = sa.Table("replacement_case", meta, pk(), tid(), sa.Column("lead_id", sa.String(36), nullable=False),
    sa.Column("reason", sa.Text, nullable=False), sa.Column("due_at", sa.DateTime, nullable=False),
    sa.Column("replacement_lead_id", sa.String(36)), sa.Column("status", sa.Text, default="open"), ts(), schema=sch("ld"))
# ---- bill ----
llm_call = sa.Table("llm_call", meta, pk(), tid(), sa.Column("job_id", sa.String(36)), sa.Column("trace_id", sa.Text),
    sa.Column("model", sa.Text, nullable=False), sa.Column("tokens_in", sa.Integer), sa.Column("tokens_out", sa.Integer),
    sa.Column("cost_rmb", sa.Numeric(10, 4), nullable=False), sa.Column("purpose", sa.Text), ts("occurred_at"), schema=sch("bill"))
cost_entry = sa.Table("cost_entry", meta, pk(), tid(), sa.Column("lead_id", sa.String(36)), sa.Column("content_id", sa.String(36)),
    sa.Column("kind", sa.Text, nullable=False), sa.Column("amount_rmb", sa.Numeric(10, 4), nullable=False),
    sa.Column("llm_call_id", sa.String(36)), sa.Column("idempotency_key", sa.Text, nullable=False), ts("occurred_at"),
    sa.UniqueConstraint("tenant_id", "idempotency_key"), schema=sch("bill"))
meter = sa.Table("meter", meta, pk(), tid(), sa.Column("lead_id", sa.String(36), nullable=False, unique=True),
    sa.Column("lead_event_id", sa.String(36), nullable=False), sa.Column("price_rmb", sa.Numeric(10, 2), nullable=False),
    sa.Column("invoice_id", sa.String(36)), sa.Column("idempotency_key", sa.Text, nullable=False), ts("occurred_at"), schema=sch("bill"))
invoice = sa.Table("invoice", meta, pk(), tid(), sa.Column("period", sa.Text, nullable=False),
    sa.Column("total_rmb", sa.Numeric(12, 2), default=0), sa.Column("status", sa.Text, default="open"),
    sa.Column("issued_at", sa.DateTime), sa.UniqueConstraint("tenant_id", "period"), schema=sch("bill"))
# ---- ct ----
content_item = sa.Table("content_item", meta, pk(), tid(), sa.Column("topic", sa.Text, nullable=False),
    sa.Column("platform", sa.Text, nullable=False), sa.Column("body", sa.Text, nullable=False),
    sa.Column("claims", J, default=list), sa.Column("aigc_label", sa.Boolean, default=True),
    sa.Column("status", sa.Text, default="draft"), sa.Column("approval_id", sa.String(36)),
    sa.Column("payload_hash", sa.Text), sa.Column("source_content_id", sa.String(36)), ts(), schema=sch("ct"))
claim_link = sa.Table("claim_link", meta, sa.Column("content_id", sa.String(36), primary_key=True),
    sa.Column("claim_path", sa.Text, primary_key=True), sa.Column("evidence_id", sa.String(36), nullable=False), schema=sch("ct"))
publish_job = sa.Table("publish_job", meta, pk(), tid(), sa.Column("content_id", sa.String(36), nullable=False),
    sa.Column("adapter", sa.Text, nullable=False), sa.Column("platform", sa.Text, nullable=False),
    sa.Column("status", sa.Text, default="pending"), sa.Column("external_url", sa.Text),
    sa.Column("attempts", sa.Integer, default=0), sa.Column("idempotency_key", sa.Text, nullable=False),
    sa.Column("last_error", sa.Text), ts(), sa.UniqueConstraint("tenant_id", "idempotency_key"), schema=sch("ct"))
channel_code = sa.Table("channel_code", meta, pk(), tid(), sa.Column("code", sa.Text, unique=True, nullable=False),
    sa.Column("platform", sa.Text, nullable=False), sa.Column("campaign", sa.Text), sa.Column("capture_asset", sa.Text), ts(), schema=sch("ct"))
engagement_thread = sa.Table("engagement_thread", meta, pk(), tid(), sa.Column("platform", sa.Text, nullable=False),
    sa.Column("external_id", sa.Text, nullable=False), sa.Column("intent", sa.Text), sa.Column("draft_reply", sa.Text),
    sa.Column("status", sa.Text, default="open"), sa.Column("lead_id", sa.String(36)),
    sa.UniqueConstraint("tenant_id", "platform", "external_id"), schema=sch("ct"))
# ---- ev ----
evidence_record = sa.Table("evidence_record", meta, pk(), tid(), sa.Column("type", sa.Text, nullable=False),
    sa.Column("status", sa.Text, default="draft"), sa.Column("metric", J), sa.Column("snapshot_hash", sa.Text),
    sa.Column("source_urls", J, default=list), sa.Column("tags", J, default=list), sa.Column("expires_at", sa.DateTime), ts(), schema=sch("ev"))
authorization = sa.Table("authorization", meta, pk(), sa.Column("evidence_id", sa.String(36), nullable=False),
    sa.Column("scope", J, nullable=False), sa.Column("consent_hash", sa.Text, nullable=False),
    sa.Column("consent_at", sa.DateTime, nullable=False), sa.Column("revoked_at", sa.DateTime), schema=sch("ev"))
audit_attestation = sa.Table("audit_attestation", meta, pk(), sa.Column("evidence_id", sa.String(36), nullable=False),
    sa.Column("auditor", sa.Text, nullable=False), sa.Column("method", sa.Text, nullable=False), ts("attested_at"), schema=sch("ev"))
remediation_task = sa.Table("remediation_task", meta, pk(), tid(), sa.Column("content_id", sa.String(36), nullable=False),
    sa.Column("evidence_id", sa.String(36), nullable=False), sa.Column("reason", sa.Text, nullable=False),
    sa.Column("due_at", sa.DateTime, nullable=False), sa.Column("status", sa.Text, default="open"),
    sa.Column("plan", J, default=dict), schema=sch("ev"))
# ---- comp ----
gate_policy = sa.Table("gate_policy", meta, pk(), sa.Column("gate", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False), sa.Column("rules", J, nullable=False),
    sa.Column("active", sa.Boolean, default=True), sa.UniqueConstraint("gate", "version"), schema=sch("comp"))
audit_log = sa.Table("audit_log", meta, pk(), sa.Column("tenant_id", sa.String(36)), sa.Column("gate", sa.Text),
    sa.Column("policy_version", sa.Integer), sa.Column("input_hash", sa.Text, nullable=False),
    sa.Column("decision", sa.Text, nullable=False), sa.Column("actor", sa.Text), sa.Column("detail", J, default=dict),
    ts("occurred_at"), schema=sch("comp"))
# ---- evl ----
eval_case = sa.Table("eval_case", meta, pk(), sa.Column("suite", sa.Text, nullable=False), sa.Column("input", J, nullable=False),
    sa.Column("expect", J, nullable=False), sa.Column("origin", sa.Text), sa.Column("active", sa.Boolean, default=True), schema=sch("evl"))
eval_run = sa.Table("eval_run", meta, pk(), sa.Column("trigger", sa.Text, nullable=False), sa.Column("pass", sa.Boolean, nullable=False),
    sa.Column("metrics", J, nullable=False), sa.Column("baseline_run_id", sa.String(36)), ts("occurred_at"), schema=sch("evl"))
# ---- ops ----
job_queue = sa.Table("job_queue", meta, pk(), sa.Column("tenant_id", sa.String(36)), sa.Column("kind", sa.Text, nullable=False),
    sa.Column("payload", J, default=dict), sa.Column("status", sa.Text, default="ready"), sa.Column("lease_owner", sa.Text),
    sa.Column("lease_until", sa.DateTime), sa.Column("checkpoint", J, default=dict), sa.Column("attempts", sa.Integer, default=0),
    sa.Column("max_attempts", sa.Integer, default=5), sa.Column("idempotency_key", sa.Text, nullable=False),
    sa.Column("next_run_at", sa.DateTime, default=lambda: utcnow()), sa.Column("last_error", sa.Text), ts(),
    sa.UniqueConstraint("kind", "idempotency_key"), schema=sch("ops"))
outbox = sa.Table("outbox", meta, pk(), sa.Column("tenant_id", sa.String(36)), sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("aggregate_id", sa.String(36)), sa.Column("payload", J, nullable=False),
    sa.Column("idempotency_key", sa.Text, nullable=False), sa.Column("dispatched_at", sa.DateTime),
    sa.Column("attempts", sa.Integer, default=0), ts("occurred_at"),
    sa.UniqueConstraint("event_type", "idempotency_key"), schema=sch("ops"))
connector_state = sa.Table("connector_state", meta, sa.Column("source", sa.Text, primary_key=True),
    sa.Column("circuit", sa.Text, default="closed"), sa.Column("failures", sa.Integer, default=0),
    sa.Column("opened_at", sa.DateTime), sa.Column("last_success_at", sa.DateTime),
    sa.Column("rate_tokens", sa.Numeric(6, 2), default=1), schema=sch("ops"))
ALL = [tenant, pack_version, catalog_item, company, signal, lead, lead_event, replacement_case, llm_call, cost_entry,
       meter, invoice, content_item, claim_link, publish_job, channel_code, engagement_thread, evidence_record,
       authorization, audit_attestation, remediation_task, gate_policy, audit_log, eval_case, eval_run, job_queue,
       outbox, connector_state]
