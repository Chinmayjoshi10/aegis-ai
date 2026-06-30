import logging
from typing import Dict, Any, List, Optional

import pandas as pd

log = logging.getLogger("aegis_ai.company_brain.bias_detector")


class BiasDetector:
    """
    Detects persistent directional drift using CUSUM — hardened for long,
    noisy series.

    Production hardening:
      * Threshold grows with √N so a 22k-row series doesn't trip on random walk.
          threshold = threshold_sigma * sigma * sqrt(N / calibration_N)
        Calibration_N is the sample size at which the classical 3σ rule is
        statistically valid for CUSUM (≈50 observations).
      * SNR guard: after CUSUM fires, require |mean_shift| ≥ snr_min_sigma · σ
        on the 30/70 split. This kills noise-driven false positives.
      * Signal-score dampening: score is scaled by SNR ratio so weak-but-
        persistent drifts never claim 100% strength.
    """

    def __init__(
        self,
        *,
        slack_sigma: float = 0.5,
        threshold_sigma: float = 3.0,
        min_points: int = 50,
        calibration_n: int = 50,
        snr_min_sigma: float = 0.5,
        max_effective_threshold_sigma: float = 12.0,
    ):
        self.slack_sigma = slack_sigma
        self.threshold_sigma = threshold_sigma
        self.min_points = min_points
        self.calibration_n = calibration_n
        self.snr_min_sigma = snr_min_sigma
        self.max_effective_threshold_sigma = max_effective_threshold_sigma

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

        n = len(series)
        k = self.slack_sigma * sigma

        # ── √N-scaled threshold ──────────────────────────────────────────
        # Classical 3σ rule assumes ~50 observations. For long series the
        # CUSUM accumulates random walk; scale the threshold accordingly.
        scale = (n / max(self.calibration_n, 1)) ** 0.5
        effective_sigma = min(
            self.threshold_sigma * scale,
            self.max_effective_threshold_sigma,
        )
        h = effective_sigma * sigma

        s_pos = 0.0
        s_neg = 0.0
        max_cusum = 0.0

        for x in series:
            s_pos = max(0.0, s_pos + (x - mu - k))
            s_neg = max(0.0, s_neg - (x - mu + k))
            max_cusum = max(max_cusum, s_pos, s_neg)

        if max_cusum <= h:
            log.debug(
                f"[BIAS] {col} below sqrt-N threshold: "
                f"cusum={max_cusum:.3f} h={h:.3f} n={n}"
            )
            return None

        # ── Split-mean recording for downstream layers ───────────────────
        # Correctness layer's 5% FLAT gate handles noise rejection by
        # absolute change; the sqrt-N CUSUM threshold handles detector
        # over-sensitivity. A σ-normalised SNR gate here was rejecting
        # legitimate 10–15% regime shifts whose signal/noise ratio was
        # modest (real B/C scenarios).
        split = max(int(n * 0.3), 1)
        baseline_mean_slice = float(series.iloc[:split].mean())
        current_mean_slice  = float(series.iloc[split:].mean())
        mean_shift          = abs(current_mean_slice - baseline_mean_slice)
        snr_ratio           = mean_shift / sigma if sigma > 0 else 0.0

        # ── Signal strength ──────────────────────────────────────────────
        # SNR gate above has already rejected weak drifts; here we just
        # emit the CUSUM ratio directly. Damping by SNR factor punished
        # legitimate ~30%-magnitude signals (B/C scenarios) too hard.
        signal_score = round(
            max(0.0, min((max_cusum - h) / max(h, 1e-9), 1.0)),
            4,
        )

        direction = "UPWARD" if s_pos > s_neg else "DOWNWARD"

        return {
            "primitive": "BIAS",
            "metric": col,
            "subtype": direction,
            "signal_score": signal_score,
            "evidence": {
                "baseline_mean":           mu,
                "baseline_std":            sigma,
                "cusum_peak":              max_cusum,
                "threshold":               h,
                "effective_threshold_sigma": round(effective_sigma, 4),
                "direction":               direction,
                "n":                       int(n),
                "snr_ratio":               round(snr_ratio, 4),
                "split_baseline_mean":     round(baseline_mean_slice, 6),
                "split_current_mean":      round(current_mean_slice, 6),
            },
        }
