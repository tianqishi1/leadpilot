"""事件信封 + outbox 同事务发布（详细设计 §5.3）。"""
import datetime as dt
from sqlalchemy.exc import IntegrityError
from leadpilot.shared import tables as T
from leadpilot.shared.ids import new_id, idem
EVENTS = ["SignalObserved","LeadCardProduced","LeadDelivered","LeadAccepted","LeadInvalidated","LeadReplaced",
          "OpportunityReported","DealClosed","EvidenceSubmitted","EvidenceAudited","EvidenceAuthorized",
          "EvidencePublished","EvidenceRevoked","EvidenceExpired","ContentApproved","ContentPublished",
          "LeadCaptured","CostRecorded","EvalRunCompleted","RolloutChanged","AuditRecorded"]
from leadpilot.shared.db import utcnow
def publish(conn, event_type, aggregate_id, payload, tenant_id=None, idem_key=None):
    assert event_type in EVENTS, event_type
    key = idem_key or idem(event_type, aggregate_id, payload.get("seq", ""))
    try:
        conn.execute(T.outbox.insert().values(id=new_id(), tenant_id=tenant_id, event_type=event_type,
            aggregate_id=aggregate_id, payload=payload, idempotency_key=key,
            occurred_at=utcnow()))
    except IntegrityError:
        pass  # 同幂等键事件已存在
    return key
