import os
from collections import defaultdict
from typing import Any, Iterable
import traceback
from datetime import datetime

from sqlalchemy import create_engine, text

# ==========================================================
# Engine bootstrap (unchanged)
# ==========================================================

def _safe_create_engine(db_url: str | None):
    if not db_url:
        return None

    if db_url.startswith("postgres") or db_url.startswith("postgresql"):
        try:
            import psycopg2  # noqa
        except ModuleNotFoundError:
            try:
                import psycopg  # noqa
            except ModuleNotFoundError:
                return None
    try:
        return create_engine(db_url, future=True, pool_pre_ping=True)
    except Exception:
        return None


DB_URL = os.environ.get("AEGIS_DATABASE_URL")
ENGINE = _safe_create_engine(DB_URL)

# ==========================================================
# Living Semantic Memory
# ==========================================================

class SemanticPG:
    """
    Unified semantic cortex over Postgres with in-memory fallback.
    """

    def __init__(self):
        self._local_tables = defaultdict(list)
        self._bootstrapped = False
        self._bootstrap()

    @property
    def enabled(self):
        return ENGINE is not None

    def _bootstrap(self):
        if self._bootstrapped:
            return
        if not ENGINE:
            self._bootstrapped = True
            return
        try:
            with ENGINE.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS semantic_facts (
                        id SERIAL PRIMARY KEY,
                        source_id TEXT,
                        source_type TEXT,
                        entity TEXT,
                        attribute TEXT,
                        value TEXT,
                        confidence DOUBLE PRECISION,
                        is_active BOOLEAN,
                        ts TIMESTAMP
                    )
                """))
            self._bootstrapped = True
        except Exception:
            print("AEGIS: SemanticPG bootstrap failed")
            print(traceback.format_exc())
            self._bootstrapped = True

    # ==========================================================
    # Compatibility layer for Schema Cortex (SAFE ADDITION)
    # ==========================================================

    def upsert(self, entity, attribute, value, unit=None, confidence=0.7, timestamp=None, source=None):
        record = {
            "source_id": source,
            "source_type": source,
            "entity": entity,
            "attribute": attribute,
            "value": str(value),
            "confidence": confidence,
            "is_active": True,
            "ts": timestamp or datetime.utcnow().isoformat()
        }
        if not ENGINE:
            self._local_tables["semantic_facts"].append(record)
            return True
        return self.insert("semantic_facts", record)

    def query_recent(self, limit=100):
        if not ENGINE:
            return list(self._local_tables.get("semantic_facts", []))[-limit:]
        rows = self.fetch_all("semantic_facts")
        return rows[-limit:]

    # ==========================================================
    # Core DB helpers (unchanged)
    # ==========================================================

    def insert(self, table, fields=None, **kwargs):
        if fields is None:
            fields = kwargs
        if not fields:
            return False
        if not ENGINE:
            self._local_tables[str(table)].append(dict(fields))
            return True
        cols = ", ".join(fields.keys())
        vals = ", ".join([f":{k}" for k in fields])
        stmt = f"INSERT INTO {table} ({cols}) VALUES ({vals})"
        with ENGINE.begin() as conn:
            conn.execute(text(stmt), fields)
        return True

    def fetch_all(self, table, **filters):
        if not ENGINE:
            rows = list(self._local_tables.get(str(table), []))
            if not filters:
                return rows
            return [r for r in rows if all(r.get(k) == v for k, v in filters.items())]

        where = " AND ".join([f"{k}=:{k}" for k in filters])
        stmt = f"SELECT * FROM {table}"
        if where:
            stmt += f" WHERE {where}"
        with ENGINE.begin() as conn:
            return list(conn.execute(text(stmt), filters).mappings().all())
