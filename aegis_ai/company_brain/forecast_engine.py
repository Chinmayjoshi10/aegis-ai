"""
AEGIS Deterministic Forecast Engine
====================================
One file. No ML. No randomness. No external deps beyond stdlib + numpy.
Same input always produces same output.
"""

import math
from typing import List, Optional
from dataclasses import dataclass


# ─────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────

@dataclass
class ForecastPoint:
    window: int
    prediction: float
    lower_bound: float
    upper_bound: float
    confidence: float
    model_used: str        # "rolling_mean" | "trend" | "volatility_adjusted"
    forecast_error: Optional[float]   # None until actual arrives
    forecast_state: str   # "STABLE" | "UNCERTAIN" | "UNSTABLE"


@dataclass
class ForecastResult:
    metric: str
    regime: str
    forecasts: List[ForecastPoint]
    forecast_confidence: float
    model_selected: str
    reasoning: str         # plain English explanation


@dataclass
class AccuracyRecord:
    window: int
    predicted: float
    actual: float
    error_pct: float
    within_band: bool


# ─────────────────────────────────────────────
# REGIME CONFIDENCE MAP
# ─────────────────────────────────────────────

REGIME_CONFIDENCE = {
    "STABLE":           1.0,
    "BASELINE_BUILDING": 0.6,
    "GROWTH":           0.8,
    "DECLINE":          0.8,
    "VOLATILE":         0.5,
    "CHAOTIC":          0.25,
}

REGIME_BAND_MULTIPLIER = {
    "STABLE":           1.0,
    "BASELINE_BUILDING": 1.5,
    "GROWTH":           1.2,
    "DECLINE":          1.2,
    "VOLATILE":         2.0,
    "CHAOTIC":          3.5,
}


# ─────────────────────────────────────────────
# CORE MATH (pure functions, no side effects)
# ─────────────────────────────────────────────

def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def _linear_slope(values: List[float]) -> float:
    """
    Least squares slope. No library needed.
    Returns slope per window step.
    """
    n = len(values)
    if n < 2:
        return 0.0
    x = list(range(n))
    sum_x = sum(x)
    sum_y = sum(values)
    sum_xy = sum(x[i] * values[i] for i in range(n))
    sum_x2 = sum(i * i for i in x)
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ─────────────────────────────────────────────
# MODEL A — Rolling Mean Forecast
# ─────────────────────────────────────────────

def rolling_mean_forecast(
    values: List[float],
    windows_ahead: int,
    std: float,
    regime: str,
) -> List[dict]:
    """
    Predict using rolling mean of recent values.
    Band expands with distance and regime uncertainty.
    """
    base = _mean(values)
    band_mult = REGIME_BAND_MULTIPLIER.get(regime, 1.5)

    results = []
    for i in range(1, windows_ahead + 1):
        band = std * band_mult * (1 + (i - 1) * 0.2)
        results.append({
            "window": i,
            "prediction": round(base, 6),
            "lower_bound": round(base - band, 6),
            "upper_bound": round(base + band, 6),
            "model": "rolling_mean",
        })
    return results


# ─────────────────────────────────────────────
# MODEL B — Linear Trend Forecast
# ─────────────────────────────────────────────

def trend_forecast(
    values: List[float],
    windows_ahead: int,
    std: float,
    regime: str,
) -> List[dict]:
    """
    Project forward using linear trend slope.
    Direction-aware. Band still widens with distance.
    """
    slope = _linear_slope(values)
    base = values[-1]
    band_mult = REGIME_BAND_MULTIPLIER.get(regime, 1.5)

    results = []
    for i in range(1, windows_ahead + 1):
        prediction = base + (slope * i)
        band = std * band_mult * (1 + (i - 1) * 0.25)
        results.append({
            "window": i,
            "prediction": round(prediction, 6),
            "lower_bound": round(prediction - band, 6),
            "upper_bound": round(prediction + band, 6),
            "model": "trend",
        })
    return results


# ─────────────────────────────────────────────
# MODEL C — Volatility-Adjusted Forecast
# ─────────────────────────────────────────────

def volatility_adjusted_forecast(
    values: List[float],
    windows_ahead: int,
    std: float,
    regime: str,
) -> List[dict]:
    """
    Use rolling mean as center but heavily widen bands
    based on observed volatility. Used for VOLATILE/CHAOTIC regimes.
    """
    base = _mean(values)
    cv = std / abs(base) if base != 0 else 1.0
    band_mult = REGIME_BAND_MULTIPLIER.get(regime, 2.0)

    results = []
    for i in range(1, windows_ahead + 1):
        volatility_band = std * band_mult * (1 + cv) * (1 + (i - 1) * 0.35)
        results.append({
            "window": i,
            "prediction": round(base, 6),
            "lower_bound": round(base - volatility_band, 6),
            "upper_bound": round(base + volatility_band, 6),
            "model": "volatility_adjusted",
        })
    return results


# ─────────────────────────────────────────────
# MODEL SELECTOR
# ─────────────────────────────────────────────

def _select_model(regime: str, slope_pct: float, std: float, mean: float) -> str:
    """
    Deterministic model selection based on regime and signal.
    No randomness. Same inputs always pick same model.
    """
    cv = std / abs(mean) if mean != 0 else 1.0

    if regime in ("CHAOTIC", "VOLATILE"):
        return "volatility_adjusted"

    if abs(slope_pct) > 0.02 and cv < 0.5:
        return "trend"

    return "rolling_mean"


# ─────────────────────────────────────────────
# FORECAST CONFIDENCE SCORE
# ─────────────────────────────────────────────

def compute_forecast_confidence(
    regime: str,
    std: float,
    mean: float,
    recent_accuracy: Optional[List[AccuracyRecord]] = None,
) -> float:
    """
    Confidence in the forecast itself.
    Separate from insight confidence.
    """
    # Base from regime
    base = REGIME_CONFIDENCE.get(regime, 0.5)

    # Penalize high coefficient of variation
    cv = std / abs(mean) if mean != 0 else 1.0
    cv_penalty = _clamp(cv * 0.3)

    # Reward if recent forecasts were accurate
    accuracy_bonus = 0.0
    if recent_accuracy:
        avg_error = _mean([r.error_pct for r in recent_accuracy])
        if avg_error < 0.05:
            accuracy_bonus = 0.1
        elif avg_error < 0.10:
            accuracy_bonus = 0.05
        elif avg_error > 0.25:
            accuracy_bonus = -0.1

    confidence = _clamp(base - cv_penalty + accuracy_bonus)
    return round(confidence, 3)


# ─────────────────────────────────────────────
# FORECAST STATE
# ─────────────────────────────────────────────

def _compute_forecast_state(confidence: float) -> str:
    if confidence >= 0.75:
        return "STABLE"
    if confidence >= 0.45:
        return "UNCERTAIN"
    return "UNSTABLE"


# ─────────────────────────────────────────────
# FORECAST vs ACTUAL TRACKING
# ─────────────────────────────────────────────

def compute_accuracy(predicted: float, actual: float, 
                     lower: float, upper: float) -> AccuracyRecord:
    """
    Compare prediction against actual value when it arrives.
    """
    error_pct = abs(predicted - actual) / abs(actual) if actual != 0 else 0.0
    within_band = lower <= actual <= upper

    return AccuracyRecord(
        window=0,
        predicted=predicted,
        actual=actual,
        error_pct=round(error_pct, 4),
        within_band=within_band,
    )


def detect_forecast_drift(
    accuracy_records: List[AccuracyRecord],
    error_threshold: float = 0.15,
    window: int = 5,
) -> dict:
    """
    If predictions are consistently wrong and getting worse —
    flag forecast instability.
    """
    if len(accuracy_records) < window:
        return {"drifting": False, "reason": "insufficient_history"}

    recent = accuracy_records[-window:]
    avg_error = _mean([r.error_pct for r in recent])
    outside_band_count = sum(1 for r in recent if not r.within_band)

    errors = [r.error_pct for r in recent]
    error_slope = _linear_slope(errors)

    drifting = (
        avg_error > error_threshold
        or outside_band_count >= (window // 2)
        or error_slope > 0.02
    )

    return {
        "drifting": drifting,
        "avg_error_pct": round(avg_error, 4),
        "outside_band_count": outside_band_count,
        "error_trend_slope": round(error_slope, 6),
        "reason": (
            "errors_increasing" if error_slope > 0.02
            else "avg_error_high" if avg_error > error_threshold
            else "stable"
        ),
    }


# ─────────────────────────────────────────────
# NARRATIVE GENERATOR
# ─────────────────────────────────────────────

def generate_forecast_narrative(result: ForecastResult) -> str:
    """
    Plain English explanation of the forecast.
    A CFO should understand this without any data background.
    """
    f = result.forecasts[0] if result.forecasts else None
    if not f:
        return "Insufficient data to generate forecast."

    direction = ""
    if result.model_selected == "trend":
        first = result.forecasts[0].prediction
        last = result.forecasts[-1].prediction
        if last > first * 1.02:
            direction = "trending upward"
        elif last < first * 0.98:
            direction = "trending downward"
        else:
            direction = "relatively flat"

    confidence_word = (
        "high" if result.forecast_confidence >= 0.75
        else "moderate" if result.forecast_confidence >= 0.45
        else "low"
    )

    regime_context = {
        "STABLE": "The system is operating in a stable regime.",
        "GROWTH": "The system is in a growth phase.",
        "DECLINE": "The system shows a declining trend.",
        "VOLATILE": "The system is volatile — treat this forecast with caution.",
        "CHAOTIC": "The system is in a chaotic state — forecast reliability is low.",
        "BASELINE_BUILDING": "Still building baseline — forecast will improve with more data.",
    }.get(result.regime, "")

    narrative_parts = [regime_context]

    if direction:
        narrative_parts.append(
            f"{result.metric} is {direction} "
            f"over the next {len(result.forecasts)} windows."
        )
    else:
        narrative_parts.append(
            f"{result.metric} is expected to remain near "
            f"{f.prediction:.2f} over the next {len(result.forecasts)} windows."
        )

    narrative_parts.append(
        f"Forecast confidence is {confidence_word} "
        f"({int(result.forecast_confidence * 100)}%). "
        f"Predicted range: [{result.forecasts[0].lower_bound:.2f} – "
        f"{result.forecasts[0].upper_bound:.2f}]."
    )

    return " ".join(p for p in narrative_parts if p)


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def run_forecast(
    metric: str,
    window_means: List[float],
    regime: str,
    slope_pct: float = 0.0,
    windows_ahead: int = 3,
    recent_accuracy: Optional[List[AccuracyRecord]] = None,
) -> Optional[ForecastResult]:
    """
    Single entry point for all forecasting.

    Args:
        metric:           column name being forecast
        window_means:     list of historical window means (oldest first)
        regime:           current confirmed regime string
        slope_pct:        normalized slope from EventStore
        windows_ahead:    how many windows to forecast
        recent_accuracy:  past AccuracyRecords for this metric (optional)

    Returns:
        ForecastResult or None if insufficient data
    """
    MIN_WINDOWS = 4

    if len(window_means) < MIN_WINDOWS:
        return None

    mean = _mean(window_means)
    std = _std(window_means)

    if mean == 0 and std == 0:
        return None

    # Select model deterministically
    model_name = _select_model(regime, slope_pct, std, mean)

    # Run selected model
    if model_name == "rolling_mean":
        raw = rolling_mean_forecast(window_means, windows_ahead, std, regime)
    elif model_name == "trend":
        raw = trend_forecast(window_means, windows_ahead, std, regime)
    else:
        raw = volatility_adjusted_forecast(window_means, windows_ahead, std, regime)

    # Compute forecast confidence
    forecast_confidence = compute_forecast_confidence(
        regime, std, mean, recent_accuracy
    )
    forecast_state = _compute_forecast_state(forecast_confidence)

    # Build ForecastPoint objects
    forecasts = [
        ForecastPoint(
            window=r["window"],
            prediction=r["prediction"],
            lower_bound=r["lower_bound"],
            upper_bound=r["upper_bound"],
            confidence=forecast_confidence,
            model_used=r["model"],
            forecast_error=None,
            forecast_state=forecast_state,
        )
        for r in raw
    ]

    # Model selection reasoning
    reasoning_map = {
        "rolling_mean": f"Regime is {regime} with low directional signal — using stable rolling mean.",
        "trend": f"Clear directional slope detected ({slope_pct:.1%}) — using trend projection.",
        "volatility_adjusted": f"Regime is {regime} — using wide volatility-adjusted bands.",
    }

    result = ForecastResult(
        metric=metric,
        regime=regime,
        forecasts=forecasts,
        forecast_confidence=forecast_confidence,
        model_selected=model_name,
        reasoning=reasoning_map[model_name],
    )

    return result


# ─────────────────────────────────────────────
# SERIALIZER — converts to dict for API response
# ─────────────────────────────────────────────

def serialize_forecast(result: ForecastResult) -> dict:
    """
    Clean dict output for API response.
    Matches the output structure from your design doc.
    """
    return {
        "metric": result.metric,
        "regime": result.regime,
        "model_selected": result.model_selected,
        "forecast_confidence": result.forecast_confidence,
        "reasoning": result.reasoning,
        "narrative": generate_forecast_narrative(result),
        "forecasts": [
            {
                "window": f.window,
                "prediction": f.prediction,
                "lower_bound": f.lower_bound,
                "upper_bound": f.upper_bound,
                "confidence": f.confidence,
                "model_used": f.model_used,
                "forecast_error": f.forecast_error,
                "forecast_state": f.forecast_state,
            }
            for f in result.forecasts
        ],
    }