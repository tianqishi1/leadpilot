"""进程内令牌桶（单 worker P0）：钉钉 20/min、发布按平台规则包。"""
import time, threading
class Bucket:
    def __init__(self, rate_per_min): self.cap = rate_per_min; self.tokens = float(rate_per_min); self.rate = rate_per_min / 60.0; self.t = time.monotonic(); self.lock = threading.Lock()
    def take(self, n=1, block=True):
        with self.lock:
            now = time.monotonic(); self.tokens = min(self.cap, self.tokens + (now - self.t) * self.rate); self.t = now
            if self.tokens >= n: self.tokens -= n; return True
            if not block: return False
            need = (n - self.tokens) / self.rate
        time.sleep(need); return self.take(n, block=False) or True
BUCKETS = {"dingtalk": Bucket(20), "publish_default": Bucket(6)}
