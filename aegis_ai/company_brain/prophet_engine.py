"""Fail-open stub for Prophet-based forecasting.

AEGIS Phase 2B references a `prophet_engine` module, but forecasting engines
(Prophet/ARIMA/SARIMA) are explicitly out of scope for this codebase version.

This module is intentionally minimal and import-safe so the API server can boot.
It provides the symbol expected by [`aegis_ai.company_brain.orchestrator.run_company_brain()`](aegis_ai/company_brain/orchestrator.py:20)
without performing any forecasting.

Constraints:
- No forecasting / ML code.
- Conservative, production-safe behavior.
- Never raise; always fail-open.
"""

from __future__ import annotations

from typing import Any, List, Optional


def run_prophet_risk_forecast(
    *,
    metric: str,
    series: List[float],
    timestamps: List[Any],
) -> Optional[dict]:
    """Return no forecast (stub).

    The orchestrator treats a falsy return as "no forecast available".
    Returning `None` keeps behavior conservative and avoids introducing
    out-of-scope forecasting behavior.
    """

    try:
        # Explicitly do nothing. Keep signature stable for callers.
        _ = (metric, series, timestamps)
        return None
    except Exception:
        # Never block server boot or request handling.
        return None


__all__ = [
    "run_prophet_risk_forecast",
]

