import sqlite3
import threading
import math
import time
from typing import List, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlite3 import Connection


class EventStore:

    # -----------------------------
    # Enterprise Defaults (Locked)
    # -----------------------------
    DEFAULT_REGIME_WINDOW = 8
    DEFAULT_SLOPE_THRESHOLD = 0.02
    DEFAULT_VOLATILITY_THRESHOLD = 0.05
    DEFAULT_VOL_DELTA_THRESHOLD = 0.02

    def __init__(self, path: str = "aegis_events.db"):

        self.db: Connection = sqlite3.connect(
            path,
            check_same_thread=False,
            isolation_level=None
        )

        # Performance + safety
        self.db.execute("PRAGMA journal_mode=WAL;")
        self.db.execute("PRAGMA synchronous=NORMAL;")

        self.lock = threading.Lock()
        self._initialize_schema()

    # ==========================================================
    # SCHEMA (Phase 3 Locked)
    # ==========================================================
    def _initialize_schema(self):

        with self.lock:

            self.db.execute("""
            CREATE TABLE IF NOT EXISTS events(
                ts REAL NOT NULL,
                tenant TEXT NOT NULL,
                domain TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL,
                confidence REAL NOT NULL
            )
            """)

            self.db.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_windows(
                tenant TEXT NOT NULL,
                domain TEXT NOT NULL,
                metric TEXT NOT NULL,
                window_start REAL NOT NULL,
                window_end REAL NOT NULL,
                mean REAL NOT NULL,
                PRIMARY KEY (tenant, domain, metric, window_start)
            )
            """)

            self.db.execute("""
            CREATE TABLE IF NOT EXISTS domain_config(
                tenant TEXT NOT NULL,
                domain TEXT NOT NULL,
                primary_metric TEXT NOT NULL,
                regime_window_size INTEGER,
                slope_threshold REAL,
                volatility_threshold REAL,
                volatility_delta_threshold REAL,
                PRIMARY KEY (tenant, domain)
            )
            """)

            self.db.execute("""
            CREATE TABLE IF NOT EXISTS domain_windows(
                tenant TEXT NOT NULL,
                domain TEXT NOT NULL,
                window_start REAL NOT NULL,
                window_end REAL NOT NULL,
                domain_mean REAL,
                slope_pct REAL,
                volatility_pct REAL,
                volatility_delta REAL,
                regime_candidate TEXT,
                regime_confirmed TEXT,
                PRIMARY KEY (tenant, domain, window_start)
            )
            """)

    # ==========================================================
    # 🚨 PRODUCTION INGESTION ENTRYPOINT (NEW)
    # ==========================================================
    def write(
        self,
        tenant: str,
        events: List[Dict],
        confidence: float,
        ts_override: Optional[float] = None,
    ):
        """
        Canonical ingestion method.
        ALL writes must go through this.
        """

        if not tenant:
            raise ValueError("tenant is required")

        if not isinstance(events, list):
            raise ValueError("events must be a list")

        if not events:
            return

        with self.lock:

            for event in events:

                # -----------------------------
                # Validation (production safety)
                # -----------------------------
                if "domain" not in event or "metric" not in event or "value" not in event:
                    raise ValueError(f"Invalid event structure: {event}")

                ts = ts_override if ts_override else event.get("ts")

                if ts is None:
                    ts = time.time()

                self.db.execute("""
                    INSERT INTO events (ts, tenant, domain, metric, value, confidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    float(ts),
                    tenant,
                    str(event["domain"]),
                    str(event["metric"]),
                    float(event["value"]),
                    float(confidence),
                ))

    # ==========================================================
    # BACKFILL
    # ==========================================================
    def backfill_time_range(self, tenant, domain, metrics,
                            start_ts, end_ts, window_size_seconds):

        current = start_ts - (start_ts % window_size_seconds)

        while current < end_ts:

            window_start = current
            window_end = current + window_size_seconds

            for metric in metrics:
                self.process_time_bucket(
                    tenant, domain, metric,
                    window_start, window_end
                )

            self.finalize_domain_window(
                tenant, domain, window_start
            )

            current += window_size_seconds

    # ==========================================================
    # METRIC LAYER (Deterministic Mean)
    # ==========================================================
    def process_time_bucket(self, tenant, domain, metric,
                            window_start, window_end):

        rows = self.db.execute("""
            SELECT value FROM events
            WHERE tenant=? AND domain=? AND metric=?
            AND ts>=? AND ts<?
        """, (tenant, domain, metric, window_start, window_end)).fetchall()

        values = [r[0] for r in rows]

        mean = sum(values) / len(values) if values else 0.0

        self.db.execute("""
            INSERT OR REPLACE INTO monitoring_windows
            VALUES (?,?,?,?,?,?)
        """, (
            tenant, domain, metric,
            window_start, window_end,
            float(mean)
        ))

    # ==========================================================
    # DOMAIN + REGIME ENGINE
    # ==========================================================
    def finalize_domain_window(self, tenant, domain, window_start):

        config = self.get_domain_config(tenant, domain)

        rows = self.db.execute("""
            SELECT metric, window_end, mean
            FROM monitoring_windows
            WHERE tenant=? AND domain=? AND window_start=?
        """, (tenant, domain, window_start)).fetchall()

        if not rows:
            return

        primary_metric = config["primary_metric"]
        window_end = rows[0][1]
        domain_mean = 0.0

        for metric, _, mean in rows:
            if metric == primary_metric and mean is not None:
                domain_mean = float(mean)
                break

        self.db.execute("""
            INSERT OR REPLACE INTO domain_windows
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            tenant,
            domain,
            window_start,
            window_end,
            float(domain_mean),
            None, None, None,
            None, None
        ))

        self._compute_and_update_regime(tenant, domain, window_start)

    # ==========================================================
    # REGIME ENGINE (UNCHANGED)
    # ==========================================================
    def _compute_and_update_regime(self, tenant, domain, window_start):

        config = self.get_domain_config(tenant, domain)

        N = config["regime_window_size"]
        slope_th = config["slope_threshold"]
        vol_th = config["volatility_threshold"]
        vol_delta_th = config["volatility_delta_threshold"]

        rows = self.db.execute("""
            SELECT window_start, domain_mean
            FROM domain_windows
            WHERE tenant=? AND domain=?
            ORDER BY window_start DESC
            LIMIT ?
        """, (tenant, domain, N)).fetchall()

        if len(rows) < N:
            candidate = "BASELINE_BUILDING"
            slope_pct = 0.0
            vol_pct = 0.0
            vol_delta = 0.0
        else:
            rows = list(reversed(rows))
            means = [float(r[1] or 0.0) for r in rows]

            slope = self._linear_regression_slope(means)
            rolling_mean = sum(means) / len(means)

            slope_pct = 0.0 if rolling_mean == 0 else slope / rolling_mean
            slope_pct = round(float(slope_pct), 10)

            mean_std = self._std(means)
            vol_pct = 0.0 if rolling_mean == 0 else mean_std / rolling_mean

            prev_vol_row = self.db.execute("""
                SELECT volatility_pct
                FROM domain_windows
                WHERE tenant=? AND domain=? AND window_start<?
                ORDER BY window_start DESC
                LIMIT 1
            """, (tenant, domain, window_start)).fetchone()

            prev_vol = 0.0
            if prev_vol_row and prev_vol_row[0] is not None:
                prev_vol = prev_vol_row[0]
            vol_delta = vol_pct - prev_vol

            if (vol_delta > vol_delta_th and vol_pct > vol_th):
                candidate = "CHAOTIC"
            elif vol_pct > vol_th:
                candidate = "VOLATILE"
            elif slope_pct < -slope_th:
                candidate = "DECLINE"
            elif slope_pct > slope_th:
                candidate = "GROWTH"
            else:
                candidate = "STABLE"

        prev_row = self.db.execute("""
            SELECT regime_candidate, regime_confirmed
            FROM domain_windows
            WHERE tenant=? AND domain=? AND window_start<?
            ORDER BY window_start DESC
            LIMIT 1
        """, (tenant, domain, window_start)).fetchone()

        if prev_row:
            prev_candidate = prev_row[0]
            prev_confirmed = prev_row[1]

            if prev_candidate == candidate:
                confirmed = candidate
            else:
                confirmed = prev_confirmed
        else:
            confirmed = candidate

        self.db.execute("""
            UPDATE domain_windows
            SET slope_pct=?,
                volatility_pct=?,
                volatility_delta=?,
                regime_candidate=?,
                regime_confirmed=?
            WHERE tenant=? AND domain=? AND window_start=?
        """, (
            float(slope_pct),
            float(vol_pct),
            float(vol_delta),
            candidate,
            confirmed,
            tenant,
            domain,
            window_start
        ))

    # ==========================================================
    # HELPERS
    # ==========================================================
    def _linear_regression_slope(self, values: List[float]) -> float:
        n = len(values)
        x = list(range(n))
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(i * i for i in x)
        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            return 0.0
        return (n * sum_xy - sum_x * sum_y) / denom

    def _std(self, values: List[float]) -> float:
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def get_domain_config(self, tenant, domain):

        row = self.db.execute("""
            SELECT primary_metric,
                   regime_window_size,
                   slope_threshold,
                   volatility_threshold,
                   volatility_delta_threshold
            FROM domain_config
            WHERE tenant=? AND domain=?
        """, (tenant, domain)).fetchone()

        if row:
            return {
                "primary_metric": row[0],
                "regime_window_size": row[1] or self.DEFAULT_REGIME_WINDOW,
                "slope_threshold": row[2] or self.DEFAULT_SLOPE_THRESHOLD,
                "volatility_threshold": row[3] or self.DEFAULT_VOLATILITY_THRESHOLD,
                "volatility_delta_threshold": row[4] or self.DEFAULT_VOL_DELTA_THRESHOLD
            }

        return {
            "primary_metric": None,
            "regime_window_size": self.DEFAULT_REGIME_WINDOW,
            "slope_threshold": self.DEFAULT_SLOPE_THRESHOLD,
            "volatility_threshold": self.DEFAULT_VOLATILITY_THRESHOLD,
            "volatility_delta_threshold": self.DEFAULT_VOL_DELTA_THRESHOLD
        }

    # ==========================================================
    # MISSING METHODS (added for static analysis)
    # ==========================================================
    def get_domains(self) -> List[str]:
        """Get list of unique domains from events table."""
        rows = self.db.execute("SELECT DISTINCT domain FROM events").fetchall()
        return [r[0] for r in rows]

    def get_monitoring_timeline(self, domain: str) -> List[Dict]:
        """Get monitoring timeline for a domain. TODO: implement properly."""
        # Placeholder: return empty list
        return []

    def get_events_between(self, domain: str, start_ts: float, end_ts: float) -> List[Dict]:
        """Get events between timestamps for a domain."""
        rows = self.db.execute(
            "SELECT ts, metric, value, confidence FROM events WHERE domain=? AND ts>=? AND ts<?",
            (domain, start_ts, end_ts)
        ).fetchall()
        return [
            {"ts": r[0], "metric": r[1], "value": r[2], "confidence": r[3]}
            for r in rows
        ]

    def clear_monitoring_results(self, domain: str) -> None:
        """Clear monitoring results for a domain. TODO: implement if needed."""
        pass

    def save_monitoring_result(
        self,
        domain: str,
        start_ts: float,
        end_ts: float,
        instability_score: float,
        moving_avg: float,
        incident_flag: bool,
        system_state: str,
    ) -> None:
        """Save monitoring result."""
        raise NotImplementedError("Monitoring result saving not implemented")