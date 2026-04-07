"""
Metric Role Resolver (Safe Default Implementation)

This module provides a stable fallback for resolving metric roles.
It ensures the system does not break if advanced role detection is absent.
"""

from typing import Dict, Any
import pandas as pd


def resolve_metric_roles(
    *,
    df: pd.DataFrame,
    baseline_stats: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    """
    Default implementation for metric role resolution.

    Returns empty mapping to keep downstream detectors functional
    without enforcing role-based logic.

    This is intentionally minimal and deterministic.
    """

    return {}