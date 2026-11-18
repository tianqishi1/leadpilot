"""polite HTTP：hosts 白名单(SSRF)/限速/缓存/熔断（详细设计 §5.4/§6.3）。"""
import time, logging, datetime as dt, threading
import httpx
from sqlalchemy import select, update
from leadpilot.shared import tables as T
from leadpilot.shared.db import tx, utcnow
log = logging.getLogger("http")
ALLOWED_HOSTS = {"www.js-eia.cn", "js-eia.cn", "new.tzxm.gov.cn", "tzxm.gov.cn", "www.ccgp.gov.cn", "ccgp.gov.cn",
                 "www.landchina.com", "landchina.com", "ggzy.jiangsu.gov.cn", "www.jiangsu.gov.cn", "sthjj.suzhou.gov.cn",
                 "www.ccgp-jiangsu.gov.cn", "ccgp-jiangsu.gov.cn",
                 "www.cebpubservice.com", "cebpubservice.com", "www.ciif-expo.com", "ciif-expo.com", "www.jobui.com", "jobui.com"}
_lock = threading.Lock(); _last = {}; _cache = {}
class SourceUnavailable(Exception): pass
def _circuit(source):
    with tx() as s:
        r = s.execute(select(T.connector_state).where(T.connector_state.c.source == source)).mappings().first()
        if not r:
            s.execute(T.connector_state.insert().values(source=source)); return "closed"
        if r["circuit"] == "open":
            if r["opened_at"] and (utcnow() - r["opened_at"]).total_seconds() > 600:
                s.execute(update(T.connector_state).where(T.connector_state.c.source == source).values(circuit="half_open"))
                return "half_open"
            raise SourceUnavailable(f"circuit open: {source}")
        return r["circuit"]
def _record(source, ok):
    with tx() as s:
        r = s.execute(select(T.connector_state).where(T.connector_state.c.source == source)).mappings().first()
        f = (r["failures"] if r else 0)
        if ok:
            s.execute(update(T.connector_state).where(T.connector_state.c.source == source).values(
                circuit="closed", failures=0, last_success_at=utcnow()))
        else:
            f += 1
            vals = {"failures": f}
            if f >= 5:
                vals.update(circuit="open", opened_at=utcnow())
                log.error("circuit open %s", source)
            s.execute(update(T.connector_state).where(T.connector_state.c.source == source).values(**vals))
def fetch(source, url, timeout=30):
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS: raise SourceUnavailable(f"host not whitelisted: {host}")
    _circuit(source)
    with _lock:
        wait = 2.0 - (time.monotonic() - _last.get(host, 0))
        if wait > 0: time.sleep(wait)
        _last[host] = time.monotonic()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LeadPilot/0.1 (polite-crawler; contact: ops@leadpilot.local)"}
    if url in _cache: headers["If-None-Match"] = _cache[url][0]
    try:
        for _hop in range(4):
            r = httpx.get(url, timeout=timeout, headers=headers, follow_redirects=False)
            if r.status_code in (301, 302, 307, 308):
                loc = r.headers.get("Location", "")
                nh = urlparse(loc).hostname or host
                if nh not in ALLOWED_HOSTS:
                    raise SourceUnavailable(f"redirect off-whitelist: {nh}")
                url = loc if loc.startswith("http") else f"https://{host}{loc}"
                continue
            break
        if r.status_code == 304:
            return _cache[url][1]
        r.raise_for_status()
        et = r.headers.get("ETag")
        if et: _cache[url] = (et, r.text)
        _record(source, True)
        return r.text
    except Exception as e:
        _record(source, False)
        raise SourceUnavailable(str(e))


def fetch_public(url, timeout=20):
    """公司官网等任意公开域: 禁私网/loopback(SSRF), 限速, 同域重定向。用于官网联系富化。"""
    import ipaddress, socket
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme not in ("http", "https"): raise SourceUnavailable("scheme")
    host = u.hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise SourceUnavailable(f"private ip blocked: {host}")
    except socket.gaierror:
        raise SourceUnavailable(f"dns fail: {host}")
    with _lock:
        wait = 2.0 - (time.monotonic() - _last.get(host, 0))
        if wait > 0: time.sleep(wait)
        _last[host] = time.monotonic()
    for _hop in range(3):
        r = httpx.get(url, timeout=timeout, follow_redirects=False,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LeadPilot/0.1 (polite-crawler)"})
        if r.status_code in (301, 302, 307, 308):
            loc = r.headers.get("Location", "")
            nh = urlparse(loc).hostname or host
            if nh != host: raise SourceUnavailable("cross-host redirect")
            url = loc if loc.startswith("http") else f"{u.scheme}://{host}{loc}"
            continue
        break
    r.raise_for_status()
    return r.text
