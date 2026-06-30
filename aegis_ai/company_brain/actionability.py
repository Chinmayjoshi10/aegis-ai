from typing import Dict, List
import numpy as np


def _to_numeric(arr) -> np.ndarray:
    return np.asarray(arr, dtype=np.float64)


def compute_actionability_likelihood(
    metric: str,
    metric_series: Dict[str, List[float]],
) -> float:
    """
    Infer how likely a metric is to be influenceable.
    Universal, behavior-based.
    """

    series = metric_series.get(metric)
    if not series or len(series) < 10:
        return 0.3  # unknown defaults low

    x = _to_numeric(series)
    if x.size == 0 or np.isnan(x).all():
        return 0.3

    x = np.nan_to_num(x, nan=0.0)

    # volatility proxy
    volatility = np.std(x) / (abs(np.mean(x)) + 1e-6)
    volatility_score = min(volatility, 1.0)

    # step-change proxy
    diffs = np.abs(np.diff(x))
    stepiness = np.percentile(diffs, 90) / (np.mean(diffs) + 1e-6)
    step_score = min(stepiness / 3.0, 1.0)

    # conservative blend
    score = 0.5 * volatility_score + 0.5 * step_score
    return max(0.0, min(score, 1.0))
