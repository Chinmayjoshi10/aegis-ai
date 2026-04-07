from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd


class DominanceDetector:
    """
    Universal Dominance Detector.

    Detects whether a column is governed by:
    1. Categorical dominance (mode frequency)
    2. Numeric point dominance (discrete repetition)
    3. Numeric range dominance (tight operating band)

    This detector:
    - DOES NOT assign confidence
    - DOES NOT decide whether to speak
    - ONLY proposes candidate insights with signal strength
    """

    def __init__(
        self,
        *,
        categorical_threshold: float = 0.6,
        range_dominance_threshold: float = 0.7,
        std_band_k: float = 0.5,
        quantile_band: tuple = (0.25, 0.75),
        min_unique_ratio_for_numeric: float = 0.05,
    ):
        self.categorical_threshold = categorical_threshold
        self.range_dominance_threshold = range_dominance_threshold
        self.std_band_k = std_band_k
        self.quantile_band = quantile_band
        self.min_unique_ratio_for_numeric = min_unique_ratio_for_numeric

    # ------------------------------------------------------------------
    # PUBLIC ENTRY POINT
    # ------------------------------------------------------------------
    def detect(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Run dominance detection across all columns.
        Returns candidate dominance insights (may be empty).
        """

        insights: List[Dict[str, Any]] = []

        for col in df.columns:
            series = df[col].dropna()
            if series.empty:
                continue

            try:
                if self._is_categorical(series):
                    insight = self._detect_categorical_dominance(col, series)
                else:
                    insight = self._detect_numeric_dominance(col, series)

                if insight:
                    insights.append(insight)

            except Exception:
                # Fail-open: one bad column must not break execution
                continue

        return insights

    # ------------------------------------------------------------------
    # TYPE CHECKS
    # ------------------------------------------------------------------
    def _is_categorical(self, series: pd.Series) -> bool:
        """
        Decide whether to treat a series as categorical.
        """
        if not pd.api.types.is_numeric_dtype(series):
            return True

        unique_ratio = series.nunique() / max(len(series), 1)
        return unique_ratio < self.min_unique_ratio_for_numeric

    # ------------------------------------------------------------------
    # CATEGORICAL DOMINANCE
    # ------------------------------------------------------------------
    def _detect_categorical_dominance(
        self, col: str, series: pd.Series
    ) -> Optional[Dict[str, Any]]:
        value_counts = series.value_counts(normalize=True)
        if value_counts.empty:
            return None

        top_value = value_counts.index[0]
        top_freq = float(value_counts.iloc[0])

        if top_freq < self.categorical_threshold:
            return None

        signal_score = self._compute_signal_score(
            coverage=top_freq,
            threshold=self.categorical_threshold,
        )

        return {
            "primitive": "DOMINANCE",
            "subtype": "CATEGORICAL",
            "metric": col,
            "signal_score": signal_score,
            "evidence": {
                "dominant_value": str(top_value),
                "coverage": top_freq,
            },
        }

    # ------------------------------------------------------------------
    # NUMERIC DOMINANCE (POINT + RANGE)
    # ------------------------------------------------------------------
    def _detect_numeric_dominance(
        self, col: str, series: pd.Series
    ) -> Optional[Dict[str, Any]]:

        # 1️⃣ Try point dominance first (exact or discretized)
        point_result = self._detect_numeric_point_dominance(col, series)
        if point_result:
            return point_result

        # 2️⃣ Try range (band) dominance
        return self._detect_numeric_range_dominance(col, series)

    # ------------------------------------------------------------------
    # NUMERIC POINT DOMINANCE
    # ------------------------------------------------------------------
    def _detect_numeric_point_dominance(
        self, col: str, series: pd.Series
    ) -> Optional[Dict[str, Any]]:

        # Discretize slightly to handle floating noise
        rounded = series.round(3)
        value_counts = rounded.value_counts(normalize=True)

        if value_counts.empty:
            return None

        top_freq = float(value_counts.iloc[0])

        if top_freq < self.categorical_threshold:
            return None

        signal_score = self._compute_signal_score(
            coverage=top_freq,
            threshold=self.categorical_threshold,
        )

        return {
            "primitive": "DOMINANCE",
            "subtype": "POINT",
            "metric": col,
            "signal_score": signal_score,
            "evidence": {
                "dominant_value": float(value_counts.index[0]),
                "coverage": top_freq,
            },
        }

    # ------------------------------------------------------------------
    # NUMERIC RANGE (BAND) DOMINANCE — CORE IMPROVEMENT
    # ------------------------------------------------------------------
    def _detect_numeric_range_dominance(
        self, col: str, series: pd.Series
    ) -> Optional[Dict[str, Any]]:

        values = series.astype(float)
        mean = values.mean()
        std = values.std()

        # ---- STD BAND (PRIMARY) ----
        if std > 0:
            lower = mean - self.std_band_k * std
            upper = mean + self.std_band_k * std
            coverage = float(((values >= lower) & (values <= upper)).mean())

            if coverage >= self.range_dominance_threshold:
                signal_score = self._compute_signal_score(
                    coverage=coverage,
                    threshold=self.range_dominance_threshold,
                )

                return {
                    "primitive": "DOMINANCE",
                    "subtype": "RANGE_STD",
                    "metric": col,
                    "signal_score": signal_score,
                    "evidence": {
                        "mean": mean,
                        "std": std,
                        "band": [lower, upper],
                        "coverage": coverage,
                    },
                }

        # ---- QUANTILE BAND (FALLBACK) ----
        q_low, q_high = self.quantile_band
        lower = values.quantile(q_low)
        upper = values.quantile(q_high)
        coverage = float(((values >= lower) & (values <= upper)).mean())

        if coverage >= self.range_dominance_threshold:
            signal_score = self._compute_signal_score(
                coverage=coverage,
                threshold=self.range_dominance_threshold,
            )

            return {
                "primitive": "DOMINANCE",
                "subtype": "RANGE_QUANTILE",
                "metric": col,
                "signal_score": signal_score,
                "evidence": {
                    "quantiles": [q_low, q_high],
                    "band": [lower, upper],
                    "coverage": coverage,
                },
            }

        return None

    # ------------------------------------------------------------------
    # SIGNAL SCORE NORMALIZATION (STEP 2A COMPATIBLE)
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_signal_score(*, coverage: float, threshold: float) -> float:
        """
        Normalize dominance strength into [0,1].
        """
        if coverage <= threshold:
            return 0.0
        return min((coverage - threshold) / (1.0 - threshold), 1.0)
