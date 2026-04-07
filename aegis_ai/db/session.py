import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv(
    "AEGIS_DB_URL",
    "sqlite:///./aegis.db"   # fallback for local dev
)

class Base(DeclarativeBase):
    pass

# SQLite notes (local dev):
# - FastAPI sync endpoints execute in a threadpool; SQLite defaults to
#   `check_same_thread=True`, which can deadlock/raise when sessions are used
#   across threads.
# - Also increase busy timeout to reduce "database is locked" stalls.
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
        "timeout": int(os.getenv("AEGIS_SQLITE_TIMEOUT", "30")),
    }

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)
