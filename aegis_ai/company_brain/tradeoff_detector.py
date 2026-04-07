from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd
from scipy.stats import pearsonr


class TradeoffDetector:
    """
    Detects structural tradeoffs between stable and risky behaviors.

    Domain-agnostic.
    Behavioral only.

    SAFE EXTENSION:
    - Optionally conditions detection on operating regime
    - Preserves all legacy behavior when regime is absent
    """

    def __init__(
        self,
        *,
        min_points: int = 200,
        corr_threshold: float = 0.4,
        p_value_threshold: float = 0.05,
        max_pairs: int = 20,
    ):
        self.min_points = min_points
        self.corr_threshold = corr_threshold
        self.p_value_threshold = p_value_threshold
        self.max_pairs = max_pairs

    # ---------------------------------------------------------
    # PUBLIC ENTRY
    # ---------------------------------------------------------
    def detect(
        self,
        df: pd.DataFrame,
        metric_stats: Dict[str, Dict[str, float]],
        *,
        regime: Dict[str, str] | None = None,   # ✅ OPTIONAL, NON-BREAKING
    ) -> List[Dict[str, Any]]:

        numeric_cols = [
            c for c in df.columns
            if c in metric_stats and pd.api.types.is_numeric_dtype(df[c])
        ]

        if len(numeric_cols) < 2:
            return []

        stable_metrics, risky_metrics = self._classify_metrics(metric_stats)

        tradeoffs: List[Dict[str, Any]] = []

        for a in stable_metrics:
            for b in risky_metrics:
                if a == b:
                    continue

                result = self._analyze_pair(df[a], df[b], a, b)
                if result:
                    # -------------------------------
                    # SAFE ADDITIVE METADATA
                    # -------------------------------
                    if regime:
                        result["regime"] = {
                            "load": regime.get("load"),
                            "stress": regime.get("stress"),
                        }

                    tradeoffs.append(result)

                if len(tradeoffs) >= self.max_pairs:
                    return tradeoffs

        return tradeoffs

    # ---------------------------------------------------------
    # METRIC CLASSIFICATION (UNCHANGED)
    # ---------------------------------------------------------
    def _classify_metrics(
        self,
        stats: Dict[str, Dict[str, float]],
    ) -> Tuple[List[str], List[str]]:

        stable = []
        risky = []

        for metric, s in stats.items():
            mean = s.get("mean")
            std = s.get("std")
            outliers = s.get("three_sigma_outliers", 0)
            count = s.get("count", 1)

            if not mean or not std or count <= 0:
                continue

            cv = std / abs(mean)

            if cv < 0.15 and outliers / count < 0.01:
                stable.append(metric)

            if outliers / count > 0.02 or cv > 0.35:
                risky.append(metric)

        return stable, risky

    # ---------------------------------------------------------
    # PAIR ANALYSIS (UNCHANGED)
    # ---------------------------------------------------------
    def _analyze_pair(
        self,
        series_a: pd.Series,
        series_b: pd.Series,
        a: str,
        b: str,
    ) -> Dict[str, Any] | None:

        paired = pd.concat([series_a, series_b], axis=1).dropna()

        if len(paired) < self.min_points:
            return None

        corr, p = pearsonr(paired.iloc[:, 0], paired.iloc[:, 1])

        if abs(corr) < self.corr_threshold or p > self.p_value_threshold:
            return None

        direction = "POSITIVE" if corr > 0 else "NEGATIVE"

        signal_score = min(abs(corr), 1.0)

        return {
            "primitive": "TRADEOFF",
            "metrics": [a, b],
            "direction": direction,
            "signal_score": signal_score,
            "evidence": {
                "correlation": corr,
                "p_value": p,
                "points": len(paired),
            },
        }
