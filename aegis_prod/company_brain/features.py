from typing import Dict, Any, List
import math


def _safe_div(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def build_metric_features(
    *,
    metric_name: str,
    reality_snapshot: Dict[str, Any],
) -> Dict[str, float]:
    """
    Build ML-safe features for a single metric
    using RealityReader outputs only.
    """

    stats = reality_snapshot.get(metric_name)
    if not stats:
        return {}

    mean = stats.get("mean", 0.0)
    median = stats.get("median", 0.0)
    std = stats.get("std", 0.0)
    min_v = stats.get("min", 0.0)
    max_v = stats.get("max", 0.0)

    null_ratio = stats.get("null_ratio", 0.0)
    zero_ratio = stats.get("zero_ratio", 0.0)

    trend = stats.get("trend", {}) or {}
    trend_slope = trend.get("slope", 0.0)
    recent_delta = trend.get("recent_delta", 0.0)

    volatility_ratio = _safe_div(std, abs(mean))

    return {
        f"{metric_name}__mean": mean,
        f"{metric_name}__median": median,
        f"{metric_name}__std": std,
        f"{metric_name}__cv": volatility_ratio,
        f"{metric_name}__min": min_v,
        f"{metric_name}__max": max_v,
        f"{metric_name}__null_ratio": null_ratio,
        f"{metric_name}__zero_ratio": zero_ratio,
        f"{metric_name}__trend_slope": trend_slope,
        f"{metric_name}__recent_delta": recent_delta,
    }


def build_feature_matrix(
    *,
    target_metric: str,
    candidate_metrics: List[str],
    reality_snapshot: Dict[str, Any],
) -> Dict[str, float]:
    """
    Build a flat feature vector for impact analysis.

    The target metric is EXCLUDED from contributors.
    """

    features: Dict[str, float] = {}

    for metric in candidate_metrics:
        if metric == target_metric:
            continue

        metric_features = build_metric_features(
            metric_name=metric,
            reality_snapshot=reality_snapshot,
        )

        features.update(metric_features)

    return features
