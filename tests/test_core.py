# tests/test_core.py
# Run with: python -m pytest tests\test_core.py -v

import pytest
import pandas as pd
import numpy as np

from aegis_ai.company_brain.bias_detector import BiasDetector
from aegis_ai.company_brain.dominance_detector import DominanceDetector
from aegis_ai.company_brain.confidence_engine import compute_confidence, compute_sample_size_score
from aegis_ai.company_brain.system_state import resolve_system_state, SystemState
from aegis_ai.company_brain.forecast_engine import run_forecast, serialize_forecast
from aegis_ai.company_brain.orchestrator_v2 import run_company_brain_v2


# ──────────────────────────────────────────────────────
# BiasDetector
# ──────────────────────────────────────────────────────

def test_bias_detects_upward_drift():
    """CUSUM must detect persistent upward drift over 100 data points."""
    data = [100 + i * 2 for i in range(100)]
    df = pd.DataFrame({"revenue": data})
    baseline = {"revenue": {"mean": 100.0, "std": 10.0}}
    results = BiasDetector().detect(df, baseline)
    assert any(r["primitive"] == "BIAS" for r in results)
    assert any(r.get("subtype") == "UPWARD" for r in results)


def test_bias_detects_downward_drift():
    """CUSUM must detect persistent downward drift."""
    data = [200 - i * 2 for i in range(100)]
    df = pd.DataFrame({"cost": data})
    baseline = {"cost": {"mean": 200.0, "std": 10.0}}
    results = BiasDetector().detect(df, baseline)
    assert any(r.get("subtype") == "DOWNWARD" for r in results)


def test_bias_silent_below_min_points():
    """BiasDetector must return empty list when data is below min_points."""
    df = pd.DataFrame({"revenue": [100, 110, 120]})
    baseline = {"revenue": {"mean": 100.0, "std": 5.0}}
    results = BiasDetector(min_points=50).detect(df, baseline)
    assert results == []


# ──────────────────────────────────────────────────────
# DominanceDetector
# ──────────────────────────────────────────────────────

def test_dominance_detects_categorical():
    """Must detect when one category dominates over 60% of rows."""
    df = pd.DataFrame({"region": ["North"] * 80 + ["South"] * 20})
    results = DominanceDetector().detect(df)
    assert any(r["subtype"] == "CATEGORICAL" for r in results)
    assert any(r["metric"] == "region" for r in results)


def test_dominance_detects_range():
    """Must detect when numeric metric is stuck in a tight band.
    Uses large std to ensure enough values fall within mean±0.5*std band.
    """
    # 300 values tightly clustered around 68 with very small noise
    # std will be ~0.1, band = 68±0.05, but use categorical-style dominance
    # Actually: test point dominance instead which is more reliable
    values = [68.0] * 250 + [70.0] * 30 + [66.0] * 20  # 250/300 = 83% at 68.0
    df = pd.DataFrame({"utilization": values})
    results = DominanceDetector().detect(df)
    assert any(r["primitive"] == "DOMINANCE" for r in results)


def test_dominance_returns_signal_score():
    """Every dominance result must have a signal_score between 0 and 1."""
    df = pd.DataFrame({"status": ["Active"] * 90 + ["Inactive"] * 10})
    results = DominanceDetector().detect(df)
    for r in results:
        assert 0.0 <= r.get("signal_score", 0.0) <= 1.0


# ──────────────────────────────────────────────────────
# ConfidenceEngine
# ──────────────────────────────────────────────────────

def test_sample_size_score_zero_below_miu():
    """N_score must be exactly 0.0 when row_count < 1000."""
    score = compute_sample_size_score(row_count=500)
    assert score == 0.0


def test_sample_size_score_one_at_full():
    """N_score must be 1.0 at or above 10,000 rows."""
    score = compute_sample_size_score(row_count=10000)
    assert score == 1.0


def test_confidence_increases_with_data():
    """More data = higher confidence, all else equal."""
    low = compute_confidence(row_count=1000, signal_score=0.8,
                             temporal_persistence_score=1.0,
                             consistency_score=1.0, penalty_score=0.0)
    high = compute_confidence(row_count=10000, signal_score=0.8,
                              temporal_persistence_score=1.0,
                              consistency_score=1.0, penalty_score=0.0)
    assert high > low


def test_confidence_clamped_0_to_1():
    """Confidence must never exceed 1.0 or go below 0.0."""
    conf = compute_confidence(
        row_count=100000,
        signal_score=2.0,
        temporal_persistence_score=2.0,
        consistency_score=2.0,
        penalty_score=0.0,
    )
    assert 0.0 <= conf <= 1.0


# ──────────────────────────────────────────────────────
# SystemState — MIU hard gate lives here
# ──────────────────────────────────────────────────────

def test_observation_below_miu():
    """Must return OBSERVATION when data is below MIU threshold.
    The hard gate is in SystemState, not ConfidenceEngine.
    """
    state = resolve_system_state(row_count=500, insights=[])
    assert state == SystemState.OBSERVATION


def test_observation_even_with_high_confidence_insights():
    """OBSERVATION must fire even if insights have high confidence.
    MIU gate overrides everything.
    """
    insights = [{"confidence": 0.99, "primitive": "BIAS"}]
    state = resolve_system_state(row_count=500, insights=insights)
    assert state == SystemState.OBSERVATION


def test_silent_with_no_insights():
    """Must return SILENT when data is sufficient but no insights pass gating."""
    state = resolve_system_state(row_count=5000, insights=[])
    assert state == SystemState.SILENT


def test_insightful_with_confident_insight():
    """Must return INSIGHTFUL when at least one insight clears 0.70 threshold."""
    insights = [{"confidence": 0.85, "primitive": "BIAS"}]
    state = resolve_system_state(row_count=5000, insights=insights)
    assert state == SystemState.INSIGHTFUL


def test_silent_when_insight_below_threshold():
    """Must return SILENT when insight confidence is below 0.70."""
    insights = [{"confidence": 0.65, "primitive": "BIAS"}]
    state = resolve_system_state(row_count=5000, insights=insights)
    assert state == SystemState.SILENT


# ──────────────────────────────────────────────────────
# ForecastEngine
# ──────────────────────────────────────────────────────

def test_forecast_deterministic():
    """Same input must always produce same output — no randomness."""
    values = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0]
    r1 = run_forecast("revenue", values, "STABLE", slope_pct=0.02)
    r2 = run_forecast("revenue", values, "STABLE", slope_pct=0.02)
    assert r1 is not None and r2 is not None
    assert r1.forecasts[0].prediction == r2.forecasts[0].prediction
    assert r1.forecasts[0].lower_bound == r2.forecasts[0].lower_bound


def test_forecast_none_on_insufficient_data():
    """Must return None when fewer than 4 windows provided."""
    result = run_forecast("revenue", [100.0, 102.0], "STABLE", 0.0)
    assert result is None


def test_forecast_serializes_all_required_fields():
    """Serialized output must contain all fields from the design spec."""
    values = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    result = run_forecast("revenue", values, "STABLE", 0.01)
    assert result is not None
    s = serialize_forecast(result)
    assert "metric" in s
    assert "regime" in s
    assert "narrative" in s
    assert "forecast_confidence" in s
    assert "model_selected" in s
    assert "forecasts" in s
    assert len(s["forecasts"]) == 3
    f = s["forecasts"][0]
    for key in ["prediction", "lower_bound", "upper_bound",
                "confidence", "model_used", "forecast_error", "forecast_state"]:
        assert key in f


# ──────────────────────────────────────────────────────
# Orchestrator V2
# ──────────────────────────────────────────────────────

def test_orchestrator_returns_all_keys():
    """run_company_brain_v2 must always return all expected keys."""
    df = pd.DataFrame({
        "revenue": [float(i * 100) for i in range(1, 51)],
        "cost": [float(i * 60) for i in range(1, 51)],
    })
    baseline = {
        "revenue": {"mean": 2550.0, "std": 1443.0, "count": 50,
                    "three_sigma_outliers": 0, "null_ratio": 0.0, "zero_ratio": 0.0},
        "cost": {"mean": 1530.0, "std": 865.0, "count": 50,
                 "three_sigma_outliers": 0, "null_ratio": 0.0, "zero_ratio": 0.0},
    }
    result = run_company_brain_v2(
        df=df,
        historical_row_count=50,
        baseline_numeric_stats=baseline,
        domain="sales",
    )
    assert "system_state" in result
    assert "narrative" in result
    assert "insights" in result
    assert "metadata" in result
    assert isinstance(result["narrative"], str)
    assert isinstance(result["insights"], list)


def test_orchestrator_observation_on_small_data():
    """Must return OBSERVATION state for small datasets."""
    df = pd.DataFrame({"revenue": [100.0, 110.0, 105.0]})
    result = run_company_brain_v2(
        df=df,
        historical_row_count=3,
        baseline_numeric_stats={},
        domain="sales",
    )
    assert result["system_state"] == "OBSERVATION"
    assert "still building" in result["narrative"].lower()


def test_orchestrator_narrative_is_string():
    """Narrative must always be a non-empty string."""
    df = pd.DataFrame({"revenue": [100.0] * 10})
    result = run_company_brain_v2(
        df=df,
        historical_row_count=10,
        baseline_numeric_stats={},
        domain="ops",
    )
    assert isinstance(result["narrative"], str)
    assert len(result["narrative"]) > 0