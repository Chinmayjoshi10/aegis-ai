import numpy as np
from typing import Dict, List


def infer_metric_roles(
    numeric_stats: Dict[str, Dict[str, float]],
) -> Dict[str, Dict[str, float]]:
    """
    Infer behavioral roles for metrics based on distributional signatures.

    Returns:
        {
          metric_name: {
              "efficiency": 0.0–1.0,
              "risk": 0.0–1.0,
              "outcome": 0.0–1.0,
              "cost_driver": 0.0–1.0
          }
        }

    Fail-open: metrics with no strong signal get low scores.
    """

    roles: Dict[str, Dict[str, float]] = {}

    for metric, s in numeric_stats.items():
        try:
            mean = abs(s.get("mean", 0.0))
            std = abs(s.get("std", 0.0))
            minv = s.get("min", 0.0)
            maxv = s.get("max", 0.0)
            zero_ratio = s.get("zero_ratio", 0.0)
            outliers = s.get("three_sigma_outliers", 0)
            count = max(s.get("count", 1), 1)

            range_width = abs(maxv - minv)
            coeff_var = std / mean if mean != 0 else 0.0
            outlier_ratio = outliers / count

            role_scores = {
                "efficiency": 0.0,
                "risk": 0.0,
                "outcome": 0.0,
                "cost_driver": 0.0,
            }

            # ----------------------------
            # Efficiency-like behavior
            # ----------------------------
            if range_width > 0 and coeff_var < 0.5:
                role_scores["efficiency"] += 0.5
            if maxv < 1000 and std < mean:
                role_scores["efficiency"] += 0.3

            # ----------------------------
            # Risk-like behavior
            # ----------------------------
            if 0.0 <= minv and maxv <= 1.0:
                role_scores["risk"] += 0.6
            if zero_ratio > 0.3:
                role_scores["risk"] += 0.2

            # ----------------------------
            # Outcome-like behavior
            # ----------------------------
            if minv < 0:
                role_scores["outcome"] += 0.6
            if outlier_ratio > 0.01:
                role_scores["outcome"] += 0.3

            # ----------------------------
            # Cost-driver behavior
            # ----------------------------
            if minv >= 0 and coeff_var > 0.8:
                role_scores["cost_driver"] += 0.4
            if outlier_ratio > 0.02:
                role_scores["cost_driver"] += 0.3

            # Clamp scores
            for k in role_scores:
                role_scores[k] = round(min(role_scores[k], 1.0), 2)

            roles[metric] = role_scores

        except Exception:
            # Fail-open: unknown metric, no roles inferred
            roles[metric] = {
                "efficiency": 0.0,
                "risk": 0.0,
                "outcome": 0.0,
                "cost_driver": 0.0,
            }

    return roles
