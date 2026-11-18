"""headless 渲染层（P1 live 校准）：playwright chromium, 白名单+限速+缓存, 仅本地渲染公开页。"""
import os, time, hashlib, pathlib, threading, logging, datetime as dt
from urllib.parse import urlparse
from leadpilot.shared.ids import env
from leadpilot.shared import http
log = logging.getLogger("headless")
_lock = threading.Lock(); _last = {}; _browser = None; _pw = None
CACHE = pathlib.Path(__file__).resolve().parents[2] / "var" / "render-cache"
def available():
    if env("HEADLESS", "0") != "1": return False
    try:
        import playwright  # noqa
        return True
    except ImportError:
        return False
def _get_browser():
    global _browser, _pw
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    return _browser
def render(url, wait_selector=None, timeout=30000, warm=None):
    host = urlparse(url).hostname or ""
    if host not in http.ALLOWED_HOSTS: raise http.SourceUnavailable(f"host not whitelisted: {host}")
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((url + dt.date.today().isoformat()).encode()).hexdigest()[:16]
    cf = CACHE / f"{key}.html"
    if cf.exists(): return cf.read_text(encoding="utf-8")
    with _lock:
        wait = 2.0 - (time.monotonic() - _last.get(host, 0))
        if wait > 0: time.sleep(wait)
        _last[host] = time.monotonic()
    try:
        b = _get_browser()
        pg = b.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) LeadPilot/0.1 (polite-headless)")
        try:
            if warm:
                pg.goto(warm, wait_until="domcontentloaded", timeout=timeout)
                pg.wait_for_timeout(1500)
            pg.goto(url, wait_until="domcontentloaded", timeout=timeout, referer=warm or None)
            if wait_selector:
                pg.wait_for_selector(wait_selector, timeout=timeout)
            else:
                pg.wait_for_timeout(2500)  # 等 JS 渲染正文
            html = pg.content()
        finally:
            pg.close()
        cf.write_text(html, encoding="utf-8")
        return html
    except Exception as e:
        raise http.SourceUnavailable(f"headless {url}: {e}")
def shutdown():
    global _browser, _pw
    if _browser: _browser.close(); _browser = None
    if _pw: _pw.stop(); _pw = None
