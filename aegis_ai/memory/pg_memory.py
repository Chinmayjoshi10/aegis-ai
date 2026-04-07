import os
import json
import hashlib
import traceback
from typing import Any

from sqlalchemy import create_engine, text


def _safe_create_engine(db_url: str | None):
    """Create engine if possible; otherwise return None.

    Postgres is optional. If a Postgres URL is configured but the driver is
    missing, DB mode is disabled and the memory backend self-heals by using the
    in-process fallback store.
    """

    if not db_url:
        return None

    if db_url.startswith("postgres") or db_url.startswith("postgresql"):
        try:
            import psycopg2  # noqa: F401
        except ModuleNotFoundError:
            try:
                import psycopg  # type: ignore  # noqa: F401
            except ModuleNotFoundError:
                return None

    try:
        return create_engine(db_url, future=True, pool_pre_ping=True)
    except Exception:
        return None


DB_URL = os.environ.get("AEGIS_DATABASE_URL")
ENGINE = _safe_create_engine(DB_URL)

class AegisPostgresMemory:
    """
    Canonical AEGIS long-term evolutionary memory cortex.
    Supports true semantic version evolution.
    """

    def __init__(self):
        self._local = {"events": [], "contracts": [], "drifts": [], "forecasts": [], "actions": []}
        self._bootstrapped = False
        self._bootstrap()

    # -------------------- low level --------------------

    def _normalize_params(self, params: Any) -> dict[str, Any] | None:
        """Normalize SQLAlchemy execute parameters.

        Safety rule: `execute(text(sql), params)` must receive ONLY dict or None.
        """

        if params is None:
            return None
        if isinstance(params, dict):
            return params if params else None
        if isinstance(params, (list, tuple)):
            # Never forward list/tuple into SQLAlchemy.
            if len(params) == 0:
                return None
            if len(params) == 1 and isinstance(params[0], dict):
                return params[0] if params[0] else None
            return None
        return None

    def _bootstrap(self) -> None:
        """Auto-create missing tables required by the PG memory backend."""

        if self._bootstrapped:
            return
        if not ENGINE:
            self._bootstrapped = True
            return

        dialect = str(getattr(ENGINE.dialect, "name", "unknown"))

        try:
            if dialect == "sqlite":
                ddl = [
                    """
                    CREATE TABLE IF NOT EXISTS aegis_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tenant TEXT,
                        domain TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        payload TEXT
                    )
                    """.strip(),
                    """
                    CREATE TABLE IF NOT EXISTS aegis_semantic_contracts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tenant TEXT,
                        version INTEGER DEFAULT 1,
                        contract TEXT,
                        contract_hash TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tenant, version)
                    )
                    """.strip(),
                    """
                    CREATE TABLE IF NOT EXISTS aegis_drift_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tenant TEXT,
                        drift_score REAL,
                        root_cause TEXT,
                        reason TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """.strip(),
                    """
                    CREATE TABLE IF NOT EXISTS aegis_forecasts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tenant TEXT,
                        forecast TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """.strip(),
                    """
                    CREATE TABLE IF NOT EXISTS aegis_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tenant TEXT,
                        action TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """.strip(),
                ]
            else:
                ddl = [
                    """
                    CREATE TABLE IF NOT EXISTS aegis_events (
                        id SERIAL PRIMARY KEY,
                        tenant TEXT,
                        domain TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        payload TEXT
                    )
                    """.strip(),
                    """
                    CREATE TABLE IF NOT EXISTS aegis_semantic_contracts (
                        id SERIAL PRIMARY KEY,
                        tenant TEXT,
                        version INTEGER DEFAULT 1,
                        contract TEXT,
                        contract_hash TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tenant, version)
                    )
                    """.strip(),
                    """
                    CREATE TABLE IF NOT EXISTS aegis_drift_history (
                        id SERIAL PRIMARY KEY,
                        tenant TEXT,
                        drift_score DOUBLE PRECISION,
                        root_cause TEXT,
                        reason TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """.strip(),
                    """
                    CREATE TABLE IF NOT EXISTS aegis_forecasts (
                        id SERIAL PRIMARY KEY,
                        tenant TEXT,
                        forecast TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """.strip(),
                    """
                    CREATE TABLE IF NOT EXISTS aegis_actions (
                        id SERIAL PRIMARY KEY,
                        tenant TEXT,
                        action TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """.strip(),
                ]

            with ENGINE.begin() as conn:
                for s in ddl:
                    conn.execute(text(s))

            self._bootstrapped = True
        except Exception:
            # Never crash the kernel due to bootstrap errors.
            print("AEGIS: AegisPostgresMemory bootstrap failed; continuing with fallback store")
            print(traceback.format_exc())
            self._bootstrapped = True

    def _execute(self, stmt, params=None):
        if not ENGINE:
            return None

        self._bootstrap()
        safe_params = self._normalize_params(params)

        try:
            with ENGINE.begin() as conn:
                if safe_params is None:
                    return conn.execute(text(stmt))
                return conn.execute(text(stmt), safe_params)
        except Exception:
            # No SQL exception should propagate into the cognition pipeline.
            print("AEGIS: DB execute failed; statement suppressed")
            print(traceback.format_exc())
            return None

    def _scalar(self, stmt, params=None):
        r = self._execute(stmt, params)
        return r.scalar() if r else None

    # -------------------- semantic memory --------------------

    def store_contract(self, tenant, contract):
        """UPSERT contract with per-tenant versioning + idempotency."""

        contract_json = json.dumps(contract, sort_keys=True)
        contract_hash = hashlib.sha256(contract_json.encode("utf-8")).hexdigest()

        # Idempotency: if this exact contract was already stored, return its version.
        existing_v = None
        if ENGINE:
            existing_v = self._scalar(
                """
                SELECT version
                FROM aegis_semantic_contracts
                WHERE tenant=:t AND contract_hash=:h
                ORDER BY version DESC
                LIMIT 1
                """,
                {"t": tenant, "h": contract_hash},
            )
        if existing_v is not None:
            return int(existing_v)

        next_version = (
            self._scalar(
                """
                SELECT COALESCE(MAX(version),0)+1
                FROM aegis_semantic_contracts
                WHERE tenant=:t
                """,
                {"t": tenant},
            )
            or 1
        )

        # UPSERT by (tenant, version) so duplicate key never crashes.
        dialect = str(getattr(getattr(ENGINE, "dialect", None), "name", "unknown")) if ENGINE else "disabled"
        if ENGINE:
            stmt = """
            INSERT INTO aegis_semantic_contracts (tenant, version, contract, contract_hash, updated_at)
            VALUES (:t,:v,:c,:h,CURRENT_TIMESTAMP)
            ON CONFLICT (tenant, version)
            DO UPDATE SET contract=excluded.contract,
                         contract_hash=excluded.contract_hash,
                         updated_at=CURRENT_TIMESTAMP
            """
            if self._execute(
                stmt,
                {"t": tenant, "v": int(next_version), "c": contract_json, "h": contract_hash},
            ):
                return int(next_version)

        # fallback memory
        self._local["contracts"].append(
            {"tenant": tenant, "version": int(next_version), "contract": contract_json, "contract_hash": contract_hash}
        )
        return int(next_version)

    def load_latest_contract(self, tenant):
        if ENGINE:
            r = self._execute("""
                SELECT contract FROM aegis_semantic_contracts
                WHERE tenant=:t ORDER BY version DESC LIMIT 1
            """, {"t": tenant}).fetchone()
            return r[0] if r else None

        contracts = [c for c in self._local["contracts"] if c["tenant"] == tenant]
        return max(contracts, key=lambda x: x["version"])["contract"] if contracts else None

    # -------------------- telemetry --------------------

    def store_event(self, tenant, domain, payload):
        if self._execute("""
            INSERT INTO aegis_events (tenant, domain, timestamp, payload)
            VALUES (:t,:d,CURRENT_TIMESTAMP,:p)
        """, {"t": tenant, "d": domain, "p": json.dumps(payload)}):
            return
        self._local["events"].append({"tenant": tenant, "domain": domain, "payload": payload})

    def store_drift(self, tenant, score, root):
        if self._execute("""
            INSERT INTO aegis_drift_history (tenant, drift_score, root_cause)
            VALUES (:t,:s,:r)
        """, {"t": tenant, "s": score, "r": json.dumps(root)}):
            return
        self._local["drifts"].append({"tenant": tenant, "score": score, "root": root})

    def store_forecast(self, tenant, forecast):
        if self._execute("""
            INSERT INTO aegis_forecasts (tenant, forecast)
            VALUES (:t,:f)
        """, {"t": tenant, "f": json.dumps(forecast)}):
            return
        self._local["forecasts"].append({"tenant": tenant, "forecast": forecast})

    def store_action(self, tenant, action):
        if self._execute("""
            INSERT INTO aegis_actions (tenant, action)
            VALUES (:t,:a)
        """, {"t": tenant, "a": json.dumps(action)}):
            return
        self._local["actions"].append({"tenant": tenant, "action": action})
