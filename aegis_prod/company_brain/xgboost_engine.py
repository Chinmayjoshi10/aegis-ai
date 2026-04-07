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


def _pearson_direction(x: np.ndarray, y: np.ndarray) -> str:
    if len(x) < 5 or len(y) < 5:
        return "unknown"
    if np.std(x) == 0 or np.std(y) == 0:
        return "unknown"

    corr = np.corrcoef(x, y)[0, 1]
    if corr > DIRECTION_EPSILON:
        return "positive"
    if corr < -DIRECTION_EPSILON:
        return "negative"
    return "unknown"


def _normalized_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
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
        X = np.tile(list(features.values()), (len(target_series), 1))
        y = np.array(target_series)

        dtrain = xgb.DMatrix(X, label=y)

        params = {
            "objective": "reg:squarederror",
            "max_depth": 3,
            "eta": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "verbosity": 0,
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
                x = np.array(series[:-lag])
                y_lagged = y[lag:]
                direction = _pearson_direction(x, y_lagged)
            elif series is not None:
                direction = _pearson_direction(np.array(series), y)

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
