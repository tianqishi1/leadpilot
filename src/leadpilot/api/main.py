from fastapi import FastAPI, Request, Depends, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
import pathlib, datetime as dt
from leadpilot.shared.ids import env, idem, new_id
from leadpilot.shared import envfile
envfile.load()
from leadpilot.shared.db import init_db
from leadpilot.contexts.tenant import service as ts
from leadpilot.contexts.lifecycle import service as lc
from leadpilot.contexts.billing import service as bs
from leadpilot.contexts.content import service as cs
from leadpilot.contexts.evidence import service as evs
from leadpilot.shared import queue, gates
ROOT = pathlib.Path(__file__).resolve().parents[3]
app = FastAPI(title="LeadPilot P0")
app.add_middleware(SessionMiddleware, secret_key=env("SESSION_SECRET", "dev-secret"))
app.mount("/static", StaticFiles(directory=str(ROOT / "web" / "static")), name="static")
tpl = Jinja2Templates(directory=str(pathlib.Path(__file__).parent / "templates"))
from leadpilot.shared import labels as _labels
tpl.env.globals.update(stage_label=_labels.stage_label, status_label=_labels.status_label, conf_label=_labels.conf_label, score_pct=_labels.score_pct, demo_tag=_labels.demo_tag)
@app.on_event("startup")
def _startup():
    init_db(); ts.seed()
class AuthRequired(Exception): pass
def auth(request: Request):
    if not request.session.get("auth"):
        raise AuthRequired()
    return True
@app.exception_handler(AuthRequired)
def _auth_handler(request: Request, exc: AuthRequired):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "login required"}, status_code=401)
    return RedirectResponse("/login", status_code=302)
def tid(request: Request):
    t = ts.tenant_by_slug(request.session.get("tenant", "own"))
    if not t: raise HTTPException(404, "tenant")
    return t["id"]
def back(page):
    from urllib.parse import quote
    safe = quote(page, safe="/:?=&")
    return RedirectResponse(safe, status_code=303, headers={"HX-Redirect": safe})
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return tpl.TemplateResponse(request, "login.html", {"request": request})
@app.post("/login")
def login(request: Request, password: str = Form(...)):
    if password != env("ADMIN_PASSWORD", "dev-admin-password"):
        return tpl.TemplateResponse(request, "login.html", {"request": request, "error": "密码错误"})
    request.session["auth"] = True
    return back("/")
@app.get("/logout")
def logout(request: Request):
    request.session.clear(); return back("/login")
@app.get("/healthz")
def healthz(): return {"ok": True}
@app.get("/readyz")
def readyz():
    from sqlalchemy import text
    from leadpilot.shared.db import engine
    with engine.connect() as c: c.execute(text("SELECT 1"))
    return {"ok": True, "deps": ["db"]}
@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    from sqlalchemy import select, func
    from leadpilot.shared import tables as T
    from leadpilot.shared.db import tx
    t = ts.tenant_by_slug("own")
    st = bs.stats(t["id"]) if t else {}
    with tx() as s:
        qd = s.execute(select(func.count()).select_from(T.job_queue).where(T.job_queue.c.status.in_(["ready", "leased"]))).scalar()
        ob = s.execute(select(func.count()).select_from(T.outbox).where(T.outbox.c.dispatched_at.is_(None))).scalar()
    lines = [f'leadpilot_queue_depth {qd}', f'leadpilot_outbox_pending {ob}',
             f'leadpilot_accept_rate {st.get("accept_rate") or 0}', f'leadpilot_cost_per_accepted {st.get("cost_per_accepted") or 0}',
             f'leadpilot_repl_open {st.get("repl_open", 0)}', f'leadpilot_repl_breached {st.get("repl_breached", 0)}']
    return "\n".join(lines) + "\n"
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, _=Depends(auth)):
    t = tid(request)
    return tpl.TemplateResponse(request, "dashboard.html", {"request": request, "stats": bs.stats(t), "repl": lc.open_replacements(t), "msg": request.query_params.get("msg", ""), "mode": env("SIGNAL_MODE", "mock")})
@app.get("/qa", response_class=HTMLResponse)
def qa_page(request: Request, _=Depends(auth)):
    return tpl.TemplateResponse(request, "qa.html", {"request": request, "leads": lc.qa_queue(tid(request))})
@app.post("/api/qa/{lid}/approve")
def qa_approve(request: Request, lid: str, _=Depends(auth)):
    lc.qa_approve(lid); return back("/qa")
@app.post("/api/qa/{lid}/drop")
def qa_drop(request: Request, lid: str, reason: str = Form("manual"), _=Depends(auth)):
    lc.qa_drop(lid, reason); return back("/qa")
@app.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request, status: str = "", _=Depends(auth)):
    return tpl.TemplateResponse(request, "leads.html", {"request": request, "leads": lc.pool(tid(request), status or None),
        "repl": lc.open_replacements(tid(request)), "status": status})
@app.post("/api/leads/{lid}/accept")
def lead_accept(request: Request, lid: str, _=Depends(auth), idempotency_key: str = Header(None)):
    try: r = lc.accept(lid, actor="console", idem_key=idempotency_key)
    except lc.WindowExpired: raise HTTPException(409, "WINDOW_EXPIRED")
    except lc.StateIllegal as e: raise HTTPException(409, str(e))
    return back("/leads")
@app.post("/api/leads/{lid}/invalidate")
def lead_invalidate(request: Request, lid: str, reason_code: str = Form(...), note: str = Form(""), _=Depends(auth)):
    lc.invalidate(lid, reason_code, note, actor="console"); return back("/leads")
@app.post("/api/leads/{lid}/stage")
def lead_stage(request: Request, lid: str, to: str = Form(...), note: str = Form(""), _=Depends(auth)):
    lc.stage(lid, to, actor="console", note=note); return back("/leads")
@app.get("/content", response_class=HTMLResponse)
def content_page(request: Request, _=Depends(auth)):
    rows, rem = cs.lists(tid(request))
    return tpl.TemplateResponse(request, "content.html", {"request": request, "items": rows, "rem": rem})
@app.post("/api/content/draft")
def content_draft(request: Request, platform: str = Form("zhihu"), _=Depends(auth)):
    cs.draft(tid(request), platform=platform); return back("/content")
@app.post("/api/content/{cid}/approve")
def content_approve(request: Request, cid: str, payload_hash: str = Form(...), _=Depends(auth)):
    try: cs.approve(cid, payload_hash, actor="console")
    except cs.StateIllegal as e: raise HTTPException(409, str(e))
    return back("/content")
@app.get("/evidence", response_class=HTMLResponse)
def evidence_page(request: Request, _=Depends(auth)):
    from sqlalchemy import select
    from leadpilot.shared import tables as T
    from leadpilot.shared.db import tx
    with tx() as s:
        rows = [dict(r) for r in s.execute(select(T.evidence_record).where(T.evidence_record.c.tenant_id == tid(request))
            .order_by(T.evidence_record.c.created_at.desc())).mappings().all()]
    return tpl.TemplateResponse(request, "evidence.html", {"request": request, "items": rows})
@app.post("/api/evidence/{eid}/revoke")
def evidence_revoke(request: Request, eid: str, _=Depends(auth)):
    evs.revoke(eid, actor="console"); return back("/evidence")
@app.post("/api/evidence/{eid}/advance")
def evidence_advance(request: Request, eid: str, to: str = Form(...), _=Depends(auth)):
    evs.transition(eid, to, actor="console"); return back("/evidence")
@app.post("/api/evidence/claims:validate")
def claims_validate(request: Request, claim: dict, _=Depends(auth)):
    return evs.validate_claim(tid(request), claim)
@app.get("/intake", response_class=HTMLResponse)
def intake_page(request: Request, _=Depends(auth)):
    return tpl.TemplateResponse(request, "intake.html", {"request": request})
@app.post("/api/signals/intake")
def signals_intake(request: Request, source: str = Form(...), company: str = Form(...), project: str = Form(...),
                   region: str = Form(""), contact_name: str = Form(""), contact_phone: str = Form(""),
                   evidence_urls: str = Form(""), raw_text: str = Form(""), _=Depends(auth)):
    import datetime as dt
    from leadpilot.contexts.signal import service as ss
    item = {"source": source, "stage": "merchant_intent" if source in ("hiring_sales", "new_branch", "exhibition", "ads_running", "new_reg") else "pre_bid",
            "project_name": project, "company_name": company, "region": region,
            "public_contact": {"name": contact_name, "phone": contact_phone} if contact_phone else {},
            "evidence_urls": [u.strip() for u in evidence_urls.splitlines() if u.strip()],
            "raw_text": raw_text or f"{project}; {company}; 联系:{contact_name} {contact_phone}",
            "observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    n = ss.ingest(tid(request), [item])
    return back("/qa" if n else "/intake")
@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, _=Depends(auth)):
    cfg = ts.config_snapshot(tid(request))
    ch = ts.get_channel_config(tid(request))
    masked = {**ch, "dingtalk_secret": (ch.get("dingtalk_secret", "")[:6] + "…" if ch.get("dingtalk_secret") else "")}
    return tpl.TemplateResponse(request, "settings.html", {"request": request, "cfg": cfg, "ch": masked, "msg": request.query_params.get("msg", "")})
@app.post("/api/settings/channel")
def settings_channel(request: Request, webhook: str = Form(""), secret: str = Form(""), _=Depends(auth)):
    ts.set_channel_config(tid(request), webhook.strip(), secret.strip())
    return back("/settings?msg=通道已保存")
@app.post("/api/settings/channel/test")
def settings_channel_test(request: Request, _=Depends(auth)):
    from leadpilot.contexts.channel import dingtalk
    r = dingtalk.test_send(tid(request))
    return back("/settings?msg=" + ("测试推送成功" if r.get("ok") else "测试失败:" + str(r.get("resp", r.get("note", "")))))
@app.get("/api/content/{cid}/export")
def content_export(request: Request, cid: str, _=Depends(auth)):
    from sqlalchemy import select
    from leadpilot.shared import tables as T
    from leadpilot.shared.db import tx
    with tx() as s:
        r = s.execute(select(T.content_item).where(T.content_item.c.id == cid, T.content_item.c.tenant_id == tid(request))).mappings().first()
    if not r: raise HTTPException(404, "content")
    return PlainTextResponse(r["body"], media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="leadpilot-{cid[:8]}.md"'})
@app.post("/api/jobs/run")
def jobs_run(request: Request, kind: str = Form(...), _=Depends(auth)):
    # 每次点击唯一幂等键(否则重复点击被去重->job_id null); 303 回看板, 不留 JSON 页
    key = queue.enqueue(kind, {}, tid(request), idem_key=idem("manual", kind, new_id()))
    return back("/?msg=已触发 " + kind + ", 稍候刷新质检/线索池")



@app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
def catch_all(request: Request, full_path: str):
    return RedirectResponse("/" if request.session.get("auth") else "/login", status_code=302)
