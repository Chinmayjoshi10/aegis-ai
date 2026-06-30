from typing import Dict, List, Any, Optional
import logging
import time
import math

import numpy as np

try:
    import xgboost as xgb
except Exception:
    xgb = None  # fail-open

from aegis_ai.company_brain.features import build_feature_matrix
from aegis_ai.company_brain.impact_models import (
    ImpactAnalysis,
    ImpactContributor,
)

logger = logging.getLogger(__name__)

# -------------------------
# Execution controls
# -------------------------

MAX_TRAIN_SECONDS = 2.0
MIN_FEATURES = 2
MODEL_VERSION = "xgb_v1.2"

DIRECTION_EPSILON = 0.05
BASE_CONFIDENCE = 0.85


def _to_numeric(arr: np.ndarray) -> np.ndarray:
    return np.asarray(arr, dtype=np.float64)


def _pearson_direction(x: np.ndarray, y: np.ndarray) -> str:
    x = _to_numeric(x)
    y = _to_numeric(y)

    if len(x) < 5 or len(y) < 5:
        return "unknown"
    if np.isnan(x).all() or np.isnan(y).all():
        return "unknown"

    x = np.nan_to_num(x, nan=0.0)
    y = np.nan_to_num(y, nan=0.0)

    if np.std(x) < 1e-6 or np.std(y) < 1e-6:
        return "unknown"

    corr = np.corrcoef(x, y)[0, 1]
    if not np.isfinite(corr):
        return "unknown"

    if corr > DIRECTION_EPSILON:
        return "positive"
    if corr < -DIRECTION_EPSILON:
        return "negative"
    return "unknown"


def _normalized_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = _to_numeric(y_true)
    y_pred = _to_numeric(y_pred)

    if y_true.size == 0 or y_pred.size == 0:
        return 1.0

    if np.isnan(y_true).all() or np.isnan(y_pred).all():
        return 1.0

    y_true = np.nan_to_num(y_true, nan=0.0)
    y_pred = np.nan_to_num(y_pred, nan=0.0)

    rmse = math.sqrt(np.mean((y_true - y_pred) ** 2))
    std = np.std(y_true)
    return rmse / std if std > 0 else 1.0


def run_xgboost_impact_analysis(
    *,
    target_metric: str,
    candidate_metrics: List[str],
    reality_snapshot: Dict[str, Any],
    metric_series: Dict[str, List[float]],
) -> Optional[ImpactAnalysis]:
    """
    Phase 2C.2 — XGBoost Impact Engine (Lag + Direction + RMSE aware)
    """

    if xgb is None:
        return None

    target_series = metric_series.get(target_metric)
    if not target_series or len(target_series) < 10:
        return None

    features = build_feature_matrix(
        target_metric=target_metric,
        candidate_metrics=candidate_metrics,
        reality_snapshot=reality_snapshot,
    )

    if len(features) < MIN_FEATURES:
        return None

    try:
        X = _to_numeric(np.tile(list(features.values()), (len(target_series), 1)))
        y = _to_numeric(target_series)

        dtrain = xgb.DMatrix(X, label=y)

        params = {
            "objective": "reg:squarederror",
            "max_depth": 3,
            "eta": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "verbosity": 0,
            "seed": 42,  # F-12: deterministic for reproducibility
        }

        start = time.time()
        model = xgb.train(params, dtrain, num_boost_round=50, verbose_eval=False)

        if time.time() - start > MAX_TRAIN_SECONDS:
            return None

        y_pred = model.predict(dtrain)

        norm_rmse = _normalized_rmse(y, y_pred)
        global_confidence = BASE_CONFIDENCE * max(0.0, 1.0 - norm_rmse)

        importance = model.get_score(importance_type="gain")
        if not importance:
            return None

        total_gain = sum(importance.values())

        contributors: List[ImpactContributor] = []

        for feature_name, gain in importance.items():
            parts = feature_name.split("__")
            metric = parts[0]
            lag = None

            if len(parts) > 1 and parts[1].startswith("lag_"):
                try:
                    lag = int(parts[1].replace("lag_", ""))
                except ValueError:
                    lag = None

            series = metric_series.get(metric)
            direction = "unknown"

            if series is not None and lag is not None and len(series) > lag:
                x = _to_numeric(series[:-lag])
                y_lagged = y[lag:]
                direction = _pearson_direction(x, y_lagged)
            elif series is not None:
                direction = _pearson_direction(_to_numeric(series), y)

            strength = gain / total_gain if total_gain > 0 else 0.0

            contributors.append(
                ImpactContributor(
                    metric=metric,
                    direction=direction,
                    strength=min(strength, 1.0),
                    confidence=global_confidence,
                    lag=lag,
                )
            )

        contributors.sort(key=lambda c: c.strength, reverse=True)

        return ImpactAnalysis(
            target_metric=target_metric,
            contributors=contributors,
            model_type="xgboost",
            model_version=MODEL_VERSION,
            global_confidence=global_confidence,
            metadata={
                "normalized_rmse": norm_rmse,
                "num_features": len(features),
                "num_samples": len(y),
                "feature_names": list(features.keys()),
                "_model": model,   # internal only
                "_X": X,           # internal only
            },
        )

    except Exception as e:
        logger.exception("XGBoost impact analysis failed (non-blocking): %s", e)
        return None
