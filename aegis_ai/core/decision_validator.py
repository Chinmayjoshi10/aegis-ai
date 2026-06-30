"""
aegis_ai/core/decision_validator.py
=====================================
Decision Validation Layer — ensures decisions are structural signals,
not noise from row order, small samples, or random variation.

Two validation strategies:
  1. Temporal split  (if ordered_data=True)
     - Split df 70/30 on time
     - Run pipeline on each half independently
     - Measure decision overlap

  2. Subsampling     (always available as fallback)
     - Run pipeline on 3 random seeds × 70% subsamples
     - Measure decision stability across subsamples

Rule: consistency < 0.5 → discard decision.

Contract:
  - Deterministic seeds (no true randomness — seeds are fixed)
  - Fail-open: if validation errors, return original decisions with
    consistency=1.0 and a warning (never block output on validator failure)
  - Does NOT re-run the full API pipeline (too slow) — runs the lightweight
    brain-only path (CUSUM + dominance) on subsets
  - Returns decisions in the same schema as synthesize_decisions()
    with one added field: "consistency": float
"""

from __future__ import annotations

import logging
import hashlib
from typing import Any

import pandas as pd
import numpy as np

log = logging.getLogger("aegis_ai.core.decision_validator")

# Fixed seeds — deterministic always
_SUBSAMPLE_SEEDS = [42, 137, 271]
_SUBSAMPLE_RATIO = 0.70
_CONSISTENCY_THRESHOLD = 0.50
_TEMPORAL_SPLIT_RATIO = 0.70


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def validate_decisions(
    decisions: list[dict[str, Any]],
    df: pd.DataFrame,
    baseline_stats: dict[str, Any],
    *,
    ordered_data: bool = False,
    time_column: str | None = None,
) -> list[dict[str, Any]]:
    """
    Validate each decision for stability.

    Args:
        decisions:      list of decisions from synthesize_decisions()
        df:             the full cleaned dataframe
        baseline_stats: {"metric": {mean, std, ...}} from RealityReader
        ordered_data:   True if a time column exists
        time_column:    name of the time column (ISO or composite)

    Returns:
        List of decisions with "consistency" field added.
        Decisions with consistency < threshold are removed.
        If validation fails entirely, original decisions are returned
        with consistency=1.0 and a "validation_warning" field.
    """
    if not decisions:
        return []

    if len(df) < 200:
        # Too small to validate meaningfully — pass through with note
        return [
            {**d, "consistency": 1.0, "validation_note": "insufficient_data_for_validation"}
            for d in decisions
        ]

    try:
        if ordered_data and time_column and time_column in df.columns:
            consistency_map = _temporal_validation(
                decisions, df, baseline_stats, time_column
            )
        else:
            consistency_map = _subsample_validation(
                decisions, df, baseline_stats
            )
    except Exception as e:
        log.error(f"[VALIDATOR] Validation failed: {e}", exc_info=True)
        # Fail-open — never block output
        return [
            {**d, "consistency": 1.0, "validation_warning": f"validator_error: {e}"}
            for d in decisions
        ]

    # Filter and annotate
    validated = []
    for decision in decisions:
        key = _decision_key(decision)
        consistency = consistency_map.get(key, 0.5)  # unknown → neutral

        if consistency < _CONSISTENCY_THRESHOLD and decision.get("type") != "REGIME_SHIFT":
            log.info(
                f"[VALIDATOR] Discarded '{decision['type']}' "
                f"— consistency={consistency:.2f} < {_CONSISTENCY_THRESHOLD}"
            )
            continue

        validated.append({**decision, "consistency": round(consistency, 3)})

    return validated


# ─────────────────────────────────────────────────────────────────────────────
# TEMPORAL VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def _temporal_validation(
    decisions: list[dict],
    df: pd.DataFrame,
    baseline_stats: dict,
    time_column: str,
) -> dict[str, float]:
    """
    Split df 70/30 on time. Run lightweight signal detection on each half.
    Consistency = fraction of decisions whose type appears in both halves.
    """
    try:
        df = df.copy()
        df["__sort"] = pd.to_datetime(df[time_column], errors="coerce")
        df = df.dropna(subset=["__sort"]).sort_values("__sort")
        df = df.drop(columns=["__sort"])
    except Exception:
        # Fallback to subsampling if time sort fails
        return _subsample_validation(decisions, df, baseline_stats)

    split_idx = int(len(df) * _TEMPORAL_SPLIT_RATIO)
    early = df.iloc[:split_idx]
    late  = df.iloc[split_idx:]

    early_types = _get_decision_types(early, baseline_stats)
    late_types  = _get_decision_types(late, baseline_stats)

    return _compute_consistency(decisions, [early_types, late_types])


# ─────────────────────────────────────────────────────────────────────────────
# SUBSAMPLING VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def _subsample_validation(
    decisions: list[dict],
    df: pd.DataFrame,
    baseline_stats: dict,
) -> dict[str, float]:
    """
    Run signal detection on 3 fixed-seed 70% subsamples.
    Consistency = fraction of runs where decision type appears.
    """
    sample_results = []

    for seed in _SUBSAMPLE_SEEDS:
        try:
            # Deterministic shuffle using fixed seed
            rng = np.random.default_rng(seed)
            indices = rng.choice(len(df), size=int(len(df) * _SUBSAMPLE_RATIO), replace=False)
            indices = sorted(indices)  # preserve original row order within sample
            subset = df.iloc[indices]
            types = _get_decision_types(subset, baseline_stats)
            sample_results.append(types)
        except Exception as e:
            log.warning(f"[VALIDATOR] Subsample seed={seed} failed: {e}")
            continue

    if not sample_results:
        # All subsamples failed — return neutral consistency
        return {_decision_key(d): 0.5 for d in decisions}

    return _compute_consistency(decisions, sample_results)


# ─────────────────────────────────────────────────────────────────────────────
# LIGHTWEIGHT SIGNAL DETECTION (for validation subsets)
# ─────────────────────────────────────────────────────────────────────────────

def _get_decision_types(
    df: pd.DataFrame,
    baseline_stats: dict,
) -> set[str]:
    """
    Run CUSUM + dominance on a df subset and return the set of
    decision TYPES that would be generated.

    This is intentionally lightweight — we only check whether the same
    pattern classes appear, not whether values are identical.
    """
    from aegis_ai.company_brain.bias_detector import BiasDetector
    from aegis_ai.company_brain.dominance_detector import DominanceDetector
    from aegis_ai.core.event_engine import normalize_events, _assign_role
    from aegis_ai.company_brain.decision_synthesizer import synthesize_decisions

    insights = []

    try:
        bias_results = BiasDetector().detect(df=df, baseline_stats=baseline_stats)
        insights.extend(bias_results or [])
    except Exception:
        pass

    try:
        dom_results = DominanceDetector().detect(df=df)
        insights.extend(dom_results or [])
    except Exception:
        pass

    if not insights:
        return set()

    # Detectors produce signal_score but NOT confidence.
    # The main pipeline adds confidence via orchestrator_v2 → compute_confidence().
    # Validator only checks decision-type overlap, so assign a working
    # confidence derived from signal_score — enough to pass the synthesizer
    # gate without distorting the type-stability check.
    for ins in insights:
        if "confidence" not in ins:
            ins["confidence"] = max(0.4, min(float(ins.get("signal_score", 0.0)), 1.0))

    # Build a minimal reality snapshot from the subset
    reality = {
        "numeric": {
            col: {
                "mean": float(df[col].mean()),
                "std": float(df[col].std()),
                "zero_ratio": float((df[col] == 0).mean()),
            }
            for col in df.select_dtypes(include="number").columns
            if col in baseline_stats
        }
    }

    try:
        events = normalize_events(insights, reality, ordered_data=False)
        decisions = synthesize_decisions(events, ordered_data=False)
        return {d["type"] for d in decisions}
    except Exception:
        return set()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _compute_consistency(
    decisions: list[dict],
    run_results: list[set[str]],
) -> dict[str, float]:
    """
    For each decision, compute fraction of validation runs that produced
    the same decision type.
    """
    n = len(run_results)
    if n == 0:
        return {}

    consistency_map = {}
    for decision in decisions:
        key  = _decision_key(decision)
        dtype = decision.get("type", "")
        hits = sum(1 for result in run_results if dtype in result)
        consistency_map[key] = round(hits / n, 4)

    return consistency_map


def _decision_key(decision: dict) -> str:
    """Stable hash key for a decision based on type + signals."""
    signals = "|".join(sorted(decision.get("signals", [])))
    raw = f"{decision.get('type', '')}|{signals}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]