from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from app.core.config import settings

_sqlite = settings.database_url.startswith("sqlite")
if _sqlite:
    # SQLite: many users read while one writes (WAL), and writers wait for each other instead of failing with "database is locked".
    engine = create_async_engine(settings.database_url, connect_args={"timeout": 30})
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL"); cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL"); cur.execute("PRAGMA foreign_keys=ON"); cur.close()
else:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=settings.db_pool_size, max_overflow=settings.db_pool_size * 2)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_db():
    async with SessionLocal() as session:
        yield session
