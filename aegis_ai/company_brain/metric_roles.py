"""
Metric Role Resolver

F-04: Wires the behavioral inference engine (metric_role_inference.py)
into the pipeline. Returns {metric_name: role_string} for metrics whose
statistical signature maps to a known role with sufficient confidence.
"""

from typing import Dict, Any
import logging

import pandas as pd

log = logging.getLogger("aegis_ai.company_brain.metric_roles")

# Behavioral score → economic role mapping
_SCORE_TO_ROLE: Dict[str, str] = {
    "efficiency": "VALUE",
    "risk":       "QUALITY",
    "outcome":    "OUTPUT",
    "cost_driver": "INPUT",
}

# Minimum score to assign a role — below this, keep UNKNOWN
_MIN_ROLE_SCORE = 0.4


def resolve_metric_roles(
    *,
    df: pd.DataFrame,
    baseline_stats: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    """
    F-04: Resolve metric roles using behavioral inference.

    Uses distributional signatures (CV, range, outlier ratio) to infer
    whether a metric behaves like an efficiency metric, risk metric, etc.

    Returns: {metric_name: "INPUT" | "OUTPUT" | "VALUE" | "QUALITY" | "UNKNOWN"}
    Fail-open: returns {} on any error.
    """
    try:
        from .metric_role_inference import infer_metric_roles
    except ImportError:
        log.warning("[METRIC_ROLES] metric_role_inference not available")
        return {}

    try:
        inferred = infer_metric_roles(baseline_stats)
    except Exception as e:
        log.warning(f"[METRIC_ROLES] inference failed: {e}")
        return {}

    roles: Dict[str, str] = {}
    for metric, scores in inferred.items():
        if not isinstance(scores, dict):
            continue
        # Pick the highest-scoring role
        best_role = max(scores, key=lambda k: scores.get(k, 0.0))
        best_score = scores.get(best_role, 0.0)
        if best_score >= _MIN_ROLE_SCORE:
            roles[metric] = _SCORE_TO_ROLE.get(best_role, "UNKNOWN")

    return roles