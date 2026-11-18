"""worker：租约 job loop + 调度 + outbox dispatch（故障域隔离外部出口）。"""
import time, logging, datetime as dt, os
from sqlalchemy import update
from leadpilot.shared import tables as T, queue, outbox
from leadpilot.shared.db import tx, init_db, utcnow
from leadpilot.shared.ids import env, idem
from leadpilot.shared import envfile
envfile.load()
from leadpilot.contexts.tenant import service as ts
from leadpilot.contexts.signal import connectors, service as ss
from leadpilot.contexts.qualification import service as qs
from leadpilot.contexts.lifecycle import service as lc
from leadpilot.contexts.billing import service as bs
from leadpilot.contexts.content import service as cs
from leadpilot.contexts.channel import dingtalk
from leadpilot.contexts.evals import runner
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("worker")
def job_crawl(job):
    total = 0
    for t in ts.all_tenants():
        for conn in connectors.connectors():
            try:
                page = conn.fetch()
                total += ss.ingest(t["id"], page["items"])
            except Exception as e:
                log.warning("connector %s fail: %s", conn.source, e)
    return total
def job_research(job): return qs.research(job)
def job_digest(job):
    tid = job["tenant_id"]
    ready = lc.pool(tid, "ready")
    if not ready: return 0
    slot = job["payload"].get("slot", dt.date.today().isoformat())
    sent = 0
    for i in range(0, len(ready), 20):  # 每消息<=20条, 防钉钉 markdown 超长
        chunk = ready[i:i + 20]
        key = idem("digest", tid, slot, i // 20)
        dingtalk.send_digest(tid, chunk, key)
        lc.deliver(tid, [l["id"] for l in chunk])  # 逐块交付, 重试只补未送块
        sent += len(chunk)
    return sent
def job_dispatch(job): return outbox.dispatch_pending(bs.HANDLERS)
def job_cleanup(job):
    with tx() as s:
        n = s.execute(update(T.signal).where(T.signal.c.ttl_at < utcnow(), T.signal.c.status.in_(["new", "matched"]))
            .values(status="expired")).rowcount
    return n
def job_content(job): return cs.draft(job["tenant_id"])
def job_publish(job): return cs.publish(job)
def job_eval(job): return runner.run(trigger="scheduled")
HANDLERS = {"crawl": job_crawl, "research": job_research, "digest": job_digest, "dispatch": job_dispatch,
            "cleanup": job_cleanup, "content": job_content, "publish": job_publish, "eval": job_eval}
KINDS = list(HANDLERS)
def run_once(kind, tenant_id=None):
    init_db(); ts.seed()
    if tenant_id is None:
        t = ts.tenant_by_slug("own"); tenant_id = t["id"] if t else None
    if kind in ("crawl", "digest", "dispatch", "cleanup", "content", "eval"):
        queue.enqueue(kind, {}, tenant_id, idem_key=idem("once", kind, utcnow().isoformat()))
    owner = "once-" + str(os.getpid())
    jobs = queue.claim([kind], owner)
    out = []
    for j in jobs:
        try:
            out.append(HANDLERS[j["kind"]](j)); queue.complete(j["id"], owner)
        except Exception as e:
            queue.fail(j["id"], owner, e); raise
    outbox.dispatch_pending(bs.HANDLERS)
    return out
def loop():
    init_db(); ts.seed()
    owner = "worker-" + str(os.getpid())
    last = {"crawl": 0, "digest": 0, "cleanup": 0, "content": 0}
    log.info("worker loop start owner=%s", owner)
    while True:
        now = time.time()
        if now - last["crawl"] > float(env("CRAWL_INTERVAL_MIN", "30")) * 60:
            for t in ts.all_tenants(): queue.enqueue("crawl", {}, t["id"], idem_key=idem("crawl", t["id"], int(now // 60))); last["crawl"] = now
        interval_h = float(env("DIGEST_INTERVAL_H", "4"))
        slot = int(now // (interval_h * 3600))
        if now - last["digest"] > interval_h * 3600:
            for t in ts.all_tenants(): queue.enqueue("digest", {"slot": slot}, t["id"], idem_key=idem("digest", t["id"], slot)); last["digest"] = now
        if now - last["cleanup"] > 3600:
            queue.enqueue("cleanup", {}, None, idem_key=idem("cleanup", int(now // 3600))); last["cleanup"] = now
        queue.enqueue("dispatch", {}, None, idem_key=idem("dispatch", int(now // 5)))
        jobs = queue.claim(KINDS, owner)
        for j in jobs:
            try:
                HANDLERS[j["kind"]](j); queue.complete(j["id"], owner)
            except Exception as e:
                log.warning("job %s fail: %s", j["kind"], e); queue.fail(j["id"], owner, e)
        time.sleep(2)
if __name__ == "__main__":
    loop()


