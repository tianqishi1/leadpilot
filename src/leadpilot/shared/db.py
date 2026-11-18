import os, pathlib, contextlib, datetime as _dt
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
ROOT = pathlib.Path(__file__).resolve().parents[3]
URL = os.environ.get("DATABASE_URL", f"sqlite:///{ROOT/'var'/'leadpilot.db'}")
IS_PG = URL.startswith("postgres")
if URL.startswith("sqlite:///"):
    p = pathlib.Path(URL.replace("sqlite:///", ""))
    if not p.is_absolute(): p = ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    URL = f"sqlite:///{p}"
engine = create_engine(URL, future=True, **({"pool_pre_ping": True} if IS_PG else {"connect_args": {"check_same_thread": False}}))
meta = MetaData()
def sch(name): return name if IS_PG else None
Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)
@contextlib.contextmanager
def tx():
    with Session() as s:
        with s.begin():
            yield s
def init_db():
    from leadpilot.shared import tables  # noqa: F401 注册表
    meta.create_all(engine)
    ensure_columns()
    from sqlalchemy import text
    with engine.begin() as c:
        c.execute(text("CREATE TABLE IF NOT EXISTS schema_version (v INTEGER NOT NULL)"))
        if not c.execute(text("SELECT v FROM schema_version")).first():
            c.execute(text("INSERT INTO schema_version VALUES (1)"))

def utcnow():
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)

def ensure_columns():
    """P0 轻量迁移: 为已存在表补新增列(sqlite/PG)。"""
    from sqlalchemy import text, inspect
    insp = inspect(engine)
    wanted = {"tenant": [("channel_config", "JSON")]}
    for tbl, cols in wanted.items():
        if not insp.has_table(tbl): continue
        have = {c["name"] for c in insp.get_columns(tbl)}
        for name, typ in cols:
            if name not in have:
                ddl = f"ALTER TABLE {tbl} ADD COLUMN {name} " + ("JSON" if IS_PG else "JSON")
                with engine.begin() as conn:
                    conn.execute(text(ddl))
