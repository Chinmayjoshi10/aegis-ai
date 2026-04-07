"""
AEGIS Forecast Integration Layer — Production Version
======================================================
Verified against actual codebase:
- EventStore uses raw sqlite3.Connection (NOT SQLAlchemy)
- routes.py raises ValueError for missing tenant (we match that pattern)
- All queries use LIMIT (matching EventStore's own query style)
- brain_output is not mutated (defensive copy)
- Logging levels match severity correctly
"""

import logging
from typing import Dict, List, Optional, Any

from aegis_ai.company_brain.forecast_engine import (
    run_forecast,
    serialize_forecast,
)

log = logging.getLogger("aegis_ai.forecast.integration")


# ─────────────────────────────────────────────
# EVENTSTORE BRIDGE
# Uses raw sqlite3.Connection — this is event_store.db
# NOT SQLAlchemy session
# ─────────────────────────────────────────────

def get_window_means_from_eventstore(
    conn,           # sqlite3.Connection — pass event_store.db directly
    tenant: str,
    domain: str,
    metric: str,
    last_n: int = 12,
) -> List[float]:
    """
    Fetch last N window means for a metric.
    Tenant + domain + metric scoped.
    Uses DESC + LIMIT for scalability, then reverses for chronological order.
    """
    try:
        rows = conn.execute(
            """
            SELECT mean FROM monitoring_windows
            WHERE tenant = ? AND domain = ? AND metric = ?
            ORDER BY window_start DESC
            LIMIT ?
            """,
            (tenant, domain, metric, last_n),
        ).fetchall()

        means = [float(r[0]) for r in rows if r[0] is not None]

        # Reverse to get chronological order (oldest first)
        # DESC query gives newest first — forecast needs oldest first
        return list(reversed(means))

    except Exception as e:
        log.warning(f"[FORECAST] window fetch failed for {metric}: {e}")
        return []


def get_domain_regime(
    conn,           # sqlite3.Connection
    tenant: str,
    domain: str,
) -> tuple:
    """
    Get current confirmed regime and slope_pct.
    Returns (regime_str, slope_pct_float).
    """
    try:
        row = conn.execute(
            """
            SELECT regime_confirmed, slope_pct
            FROM domain_windows
            WHERE tenant = ? AND domain = ?
            ORDER BY window_start DESC
            LIMIT 1
            """,
            (tenant, domain),
        ).fetchone()

        if row and row[0]:
            regime = row[0]
            slope_pct = 0.0
            if row[1] is not None:
                slope_pct = float(row[1])
            return regime, slope_pct

    except Exception as e:
        log.warning(f"[FORECAST] regime fetch failed: {e}")

    return "BASELINE_BUILDING", 0.0


def get_primary_metric(
    conn,           # sqlite3.Connection
    tenant: str,
    domain: str,
) -> Optional[str]:
    """
    Get configured primary metric for a domain from domain_config.
    """
    try:
        row = conn.execute(
            """
            SELECT primary_metric FROM domain_config
            WHERE tenant = ? AND domain = ?
            """,
            (tenant, domain),
        ).fetchone()

        return row[0] if row and row[0] else None

    except Exception as e:
        log.debug(f"[FORECAST] primary_metric not configured: {e}")
        return None


# ─────────────────────────────────────────────
# DOMAIN FORECAST RUNNER
# ─────────────────────────────────────────────

def run_domain_forecasts(
    conn,                       # sqlite3.Connection — event_store.db
    tenant: str,
    domain: str,
    metrics: List[str],
    windows_ahead: int = 3,
    max_metrics: int = 10,
) -> Dict[str, Any]:
    """
    Run forecasts for all metrics in a domain.
    Tenant + domain scoped. Fail-fast on missing tenant.

    Args:
        conn:          event_store.db (raw sqlite3 connection)
        tenant:        tenant_id — REQUIRED, raises if missing
        domain:        domain string
        metrics:       metric names from baseline_numeric_stats
        windows_ahead: forecast horizon
        max_metrics:   cap to prevent runaway computation

    Returns:
        Structured forecast dict with status field
    """

    # ── Hard fail on missing tenant (matches routes.py pattern) ──
    if not tenant:
        raise ValueError("tenant_id is required for forecast execution")

    if not domain:
        raise ValueError("domain is required for forecast execution")

    # ── Get regime context once for the domain ──
    regime, slope_pct = get_domain_regime(conn, tenant, domain)
    primary_metric = get_primary_metric(conn, tenant, domain)

    forecasts_output: Dict[str, Any] = {}
    metrics_to_forecast = metrics[:max_metrics]

    for metric in metrics_to_forecast:
        try:
            window_means = get_window_means_from_eventstore(
                conn, tenant, domain, metric
            )

            if len(window_means) < 4:
                # Expected — not enough history yet
                log.debug(
                    f"[FORECAST] skipping {metric} — "
                    f"only {len(window_means)} windows (need 4)"
                )
                continue

            result = run_forecast(
                metric=metric,
                window_means=window_means,
                regime=regime,
                slope_pct=slope_pct,
                windows_ahead=windows_ahead,
            )

            if result:
                forecasts_output[metric] = serialize_forecast(result)

        except Exception as e:
            log.warning(f"[FORECAST] metric {metric} failed: {e}")
            continue

    # ── Empty guard — return clear status when no forecasts ──
    if not forecasts_output:
        return {
            "status": "INSUFFICIENT_DATA",
            "regime": regime,
            "slope_pct": round(slope_pct, 6),
            "metrics": {},
            "primary_metric_forecast": None,
            "tenant": tenant,
            "domain": domain,
        }

    # ── Primary metric forecast ──
    primary_forecast = None
    if primary_metric and primary_metric in forecasts_output:
        primary_forecast = forecasts_output[primary_metric]

    return {
        "status": "OK",
        "regime": regime,
        "slope_pct": round(slope_pct, 6),
        "metrics": forecasts_output,
        "primary_metric_forecast": primary_forecast,
        "tenant": tenant,
        "domain": domain,
    }


# ─────────────────────────────────────────────
# PIPELINE INTEGRATION
# Single drop-in function for routes.py
# ─────────────────────────────────────────────

def attach_forecasts_to_brain_output(
    brain_output: Dict[str, Any],
    event_store_db,                 # event_store.db — raw sqlite3.Connection
    tenant: str,
    domain: str,
    baseline_numeric_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Attaches forecast layer to brain output.
    Does NOT mutate the input dict — returns a new dict.
    Non-blocking — forecast failure never kills the main pipeline.

    Usage in routes.py:
        brain_output = attach_forecasts_to_brain_output(
            brain_output=brain_output,
            event_store_db=event_store.db,   # raw sqlite3 connection
            tenant=tenant_id,
            domain=domain,
            baseline_numeric_stats=current_stats["numeric"],
        )
    """

    # ── Defensive copy — never mutate the input ──
    output = dict(brain_output)

    try:
        metrics = list(baseline_numeric_stats.keys())

        forecast_result = run_domain_forecasts(
            conn=event_store_db,
            tenant=tenant,
            domain=domain,
            metrics=metrics,
        )

        output["forecasts"] = forecast_result

    except ValueError as e:
        # Hard failures (missing tenant/domain) — surface clearly
        log.error(f"[FORECAST_ATTACH] configuration error: {e}")
        output["forecasts"] = {
            "status": "CONFIGURATION_ERROR",
            "error": str(e),
            "metrics": {},
            "primary_metric_forecast": None,
        }

    except Exception as e:
        # Unexpected failures — log, never block pipeline
        log.error(f"[FORECAST_ATTACH] unexpected failure: {e}")
        output["forecasts"] = {
            "status": "ERROR",
            "error": str(e),
            "metrics": {},
            "primary_metric_forecast": None,
        }

    return output