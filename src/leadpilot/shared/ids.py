import os, uuid, hashlib
def new_id() -> str: return uuid.uuid4().hex
def idem(*parts) -> str: return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]
def env(k, d=""): return os.environ.get(k, d)
