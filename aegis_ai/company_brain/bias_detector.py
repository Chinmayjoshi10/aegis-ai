from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


class BiasDetector:
    """
    Detects persistent directional drift using CUSUM.

    This detector:
    - Ignores point anomalies
    - Detects sustained deviation
    - Produces signal_score only
    """

    def __init__(
        self,
        *,
        slack_sigma: float = 0.5,
        threshold_sigma: float = 3.0,
        min_points: int = 50,
    ):
        self.slack_sigma = slack_sigma
        self.threshold_sigma = threshold_sigma
        self.min_points = min_points

    # ------------------------------------------------------------
    # PUBLIC ENTRY POINT
    # ------------------------------------------------------------
    def detect(
        self,
        df: pd.DataFrame,
        baseline_stats: Dict[str, Dict[str, float]],
    ) -> List[Dict[str, Any]]:
        """
        Runs bias detection for all numeric columns.

        baseline_stats format:
        {
          metric: { "mean": μ, "std": σ }
        }
        """

        insights: List[Dict[str, Any]] = []

        for col in df.columns:
            if col not in baseline_stats:
                continue

            series = df[col].dropna()
            if len(series) < self.min_points:
                continue

            if not pd.api.types.is_numeric_dtype(series):
                continue

            try:
                baseline = baseline_stats[col]
                result = self._detect_bias(col, series, baseline)
                if result:
                    insights.append(result)

            except Exception:
                # Fail-open
                continue

        return insights

    # ------------------------------------------------------------
    # CORE CUSUM LOGIC
    # ------------------------------------------------------------
    def _detect_bias(
        self,
        col: str,
        series: pd.Series,
        baseline: Dict[str, float],
    ) -> Optional[Dict[str, Any]]:

        mu = baseline.get("mean")
        sigma = baseline.get("std")

        if mu is None or sigma is None or sigma <= 0:
            return None

        k = self.slack_sigma * sigma
        h = self.threshold_sigma * sigma

        s_pos = 0.0
        s_neg = 0.0
        max_cusum = 0.0

        for x in series:
            s_pos = max(0.0, s_pos + (x - mu - k))
            s_neg = max(0.0, s_neg - (x - mu + k))
            max_cusum = max(max_cusum, s_pos, s_neg)

        if max_cusum <= h:
            return None

        # --------------------------------------------------------
        # Signal strength normalization
        # --------------------------------------------------------
        signal_score = min((max_cusum - h) / h, 1.0)

        direction = "UPWARD" if s_pos > s_neg else "DOWNWARD"

        return {
            "primitive": "BIAS",
            "metric": col,
            "subtype": direction,
            "signal_score": signal_score,
            "evidence": {
                "baseline_mean": mu,
                "baseline_std": sigma,
                "cusum_peak": max_cusum,
                "threshold": h,
                "direction": direction,
            },
        }
