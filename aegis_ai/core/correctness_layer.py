"""
aegis_ai/core/correctness_layer.py
=====================================
Correctness Layer — post-signal validation for system integrity.

Runs AFTER signal detection, BEFORE decision synthesis.
Ensures every signal that reaches the decision layer reflects data reality.

Four responsibilities:
  1. SIGNAL DIRECTION VALIDATION — verify CUSUM direction against actual means
  2. COLUMN TYPE ENFORCEMENT — reject identifier columns that slipped past gates
  3. SIGNED METRIC ANNOTATION — flag metrics with negative values and compute split stats
  4. CONSISTENCY STAMP — tag every validated signal so downstream has single source of truth

Contract:
  - Deterministic: same input → same output
  - Fail-open: invalid signals are REMOVED, never modified silently
  - No domain logic, no ML, no LLM
  - Must run on every dataset, every pipeline invocation
"""

from __future__ import annotations

import re
import logging
from typing import Any

import pandas as pd
import numpy as np

log = logging.getLogger("aegis_ai.core.correctness_layer")


# ─────────────────────────────────────────────────────────────────────────────
# COLUMN TYPE CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

# Classifier thresholds
_UNIQUE_RATIO_ID_THRESHOLD = 0.50       # >50% unique → likely identifier
_CV_ID_THRESHOLD           = 2.0        # coefficient of variation >2 + high unique → ID
_MIN_ROWS_FOR_CLASSIFICATION = 20

# CamelCase and suffix patterns for identifiers
_ID_NAME_PATTERN = re.compile(
    r"\b(id|code|key|number|no|num|pk|fk|ref|uuid|guid|sku|serial|index|idx)\b"
    r"|(?:No|ID|Id|Code|Key|Num|Ref|Idx)$",
    re.IGNORECASE,
)


def classify_column(col: str, series: pd.Series) -> str:
    """
    Classify a numeric column as 'metric' or 'identifier'.

    Heuristics (deterministic):
      - Name matches ID pattern → identifier
      - High cardinality + near-monotonic → identifier
      - Unique ratio > threshold + high CV → identifier
      - Otherwise → metric

    Returns: 'metric' | 'identifier'
    """
    # Gate 1: Name-based
    if _ID_NAME_PATTERN.search(col):
        return "identifier"

    s = series.dropna()
    n = len(s)
    if n < _MIN_ROWS_FOR_CLASSIFICATION:
        return "metric"  # too few rows to classify, default to metric

    n_unique = s.nunique()
    unique_ratio = n_unique / n

    # Gate 2: High unique ratio (>50% unique values)
    if unique_ratio > _UNIQUE_RATIO_ID_THRESHOLD:
        # Confirm with CV check — real metrics have lower CV than IDs
        mean = abs(float(s.mean()))
        std = float(s.std())
        cv = (std / mean) if mean > 0 else 0.0
        if cv > _CV_ID_THRESHOLD:
            return "identifier"

        # Gate 3: Monotonic check — identifiers tend to be monotonically increasing
        if n_unique == n:
            # Every value is unique — check if sorted
            sorted_vals = s.values
            if np.all(sorted_vals[1:] >= sorted_vals[:-1]) or np.all(sorted_vals[1:] <= sorted_vals[:-1]):
                return "identifier"

    return "metric"


# ─────────────────────────────────────────────────────────────────────────────
# SIGNED METRIC ANNOTATION
# ─────────────────────────────────────────────────────────────────────────────

def compute_signed_metric_context(series: pd.Series) -> dict[str, Any] | None:
    """
    If a numeric column contains negative values in a predominantly positive
    distribution, compute split statistics.

    Returns None if no negative values exist.
    Returns context dict otherwise.
    """
    s = series.dropna()
    if len(s) == 0:
        return None

    n_total = len(s)
    n_negative = int((s < 0).sum())

    if n_negative == 0:
        return None

    n_positive = int((s > 0).sum())
    n_zero = int((s == 0).sum())
    positive_sum = float(s[s > 0].sum())
    negative_sum = float(s[s < 0].sum())
    negative_ratio = n_negative / n_total

    return {
        "is_signed": True,
        "positive_count": n_positive,
        "negative_count": n_negative,
        "zero_count": n_zero,
        "positive_sum": round(positive_sum, 4),
        "negative_sum": round(negative_sum, 4),
        "negative_ratio": round(negative_ratio, 4),
        "net_sum": round(positive_sum + negative_sum, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL DIRECTION VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

_FLAT_THRESHOLD = 0.05  # ±5% — signals within this band are noise-floor.
#   Hardened from ±1% → ±5% (W1 fix):
#   1% is within the jitter of mean-slices on noisy 20k-row series and let
#   false positives escape the FLAT gate. 5% is the minimum change most
#   business KPIs would describe as "moving".


def _validate_signal_direction(
    signal: dict[str, Any],
    df: pd.DataFrame,
    baseline_stats: dict[str, Any],
    time_column: str | None = None,
) -> dict[str, Any] | None:
    """
    Strict direction enforcement against actual data.

    Rules:
      change = (current_mean - baseline_mean) / baseline_mean

      actual_direction:
        UPWARD   if change >  0.01
        DOWNWARD if change < -0.01
        FLAT     if -0.01 <= change <= 0.01

      Enforcement:
        FLAT                              → REJECT (signal is noise)
        detected == actual                → VALIDATE, stamp validated_direction
        detected != actual (non-FLAT)    → OVERRIDE detected with actual, stamp corrected

      Edge cases:
        baseline_mean == 0               → REJECT (avoid division error)
        len(series) < 20                 → REJECT (insufficient data)
    """
    metric = signal.get("metric", "")
    detected_direction = signal.get("direction", "UNKNOWN")

    # F-01: STRUCTURAL signals (dominance) are non-directional.
    # They describe concentration, not temporal change. Bypass
    # direction validation — pass through with validation stamp.
    if detected_direction == "STRUCTURAL":
        out = {**signal}
        out["validated_direction"] = "STRUCTURAL"
        out["validation_status"] = "validated"
        out["actual_change"] = 0.0
        out["correctness"] = {
            "status": "validated",
            "validated_direction": "STRUCTURAL",
            "actual_change": 0.0,
        }
        return out

    if metric not in df.columns:
        return None

    # ── Sort by time column before splitting ─────────────────────────
    if time_column and time_column in df.columns:
        df_sorted = df.sort_values(time_column)
    else:
        df_sorted = df  # fall back to row order

    series = df_sorted[metric].dropna()
    if len(series) < 20:
        log.info(f"[CORRECTNESS] Rejected {metric}: insufficient rows ({len(series)})")
        return None

    # ── Compute window means ─────────────────────────────────────────
    n = len(series)
    if not time_column:
        # Unordered data: disable temporal drift, set change to 0
        baseline_mean = float(series.mean())
        current_mean = baseline_mean
    elif n < 10:
        baseline_mean = float(series.mean())
        current_mean = baseline_mean
    else:
        split = int(n * 0.3)
        baseline_mean = float(series.iloc[:split].mean())
        current_mean  = float(series.iloc[split:].mean())

    # Edge case: zero baseline → division undefined → reject
    if abs(baseline_mean) < 1e-12:
        log.info(f"[CORRECTNESS] Rejected {metric}: baseline_mean ≈ 0")
        return None

    # ── Actual change (signed, relative) ────────────────────────────
    change = (current_mean - baseline_mean) / abs(baseline_mean)

    # ── Determine actual direction ───────────────────────────────────
    if change > _FLAT_THRESHOLD:
        actual_direction = "UPWARD"
    elif change < -_FLAT_THRESHOLD:
        actual_direction = "DOWNWARD"
    else:
        actual_direction = "FLAT"

    # ── Enforce correctness ──────────────────────────────────────────
    # FLAT means the metric is NOT moving. No primitive should override
    # data reality. TRADEOFF is the only exception because it describes
    # a structural relationship (non-directional). STRUCTURAL direction
    # signals are also exempt (concentration, not temporal change).
    if actual_direction == "FLAT" and signal.get("primitive") not in ("TRADEOFF",) and signal.get("direction") != "STRUCTURAL":
        log.info(
            f"[CORRECTNESS] Rejected {metric}: change={change:.4f} within ±{_FLAT_THRESHOLD} (FLAT)"
        )
        return None

    out = {**signal}
    out["validated_direction"] = actual_direction
    out["actual_change"]       = round(change, 6)

    if detected_direction == actual_direction:
        out["validation_status"] = "validated"
        log.debug(f"[CORRECTNESS] Validated {metric}: {actual_direction} change={change:.4f}")
    else:
        # Direction is wrong — override with truth
        log.warning(
            f"[CORRECTNESS] Corrected {metric}: "
            f"detected={detected_direction} → actual={actual_direction} "
            f"(change={change:.4f})"
        )
        out["direction"]         = actual_direction   # single source of truth
        out["validation_status"] = "corrected"

    # Backward-compatible correctness block
    out["correctness"] = {
        "status":           out["validation_status"],
        "validated_direction": actual_direction,
        "actual_change":    round(change, 6),
        "baseline_mean":    round(baseline_mean, 6),
        "current_mean":     round(current_mean, 6),
    }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def validate_signals(
    events: list[dict[str, Any]],
    df: pd.DataFrame,
    baseline_stats: dict[str, Any],
    time_column: str | None = None,
    valid_metrics: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Run the full correctness layer on a list of normalised events.

    Steps:
      0. Metric allowlist enforcement — reject non-metric columns
      1. Column type enforcement — reject identifier columns
      2. Direction validation — verify/correct/reject each signal
      3. Signed metric annotation — attach negative-value context

    Args:
        events:         normalised events from event_engine.normalize_events()
        df:             the working DataFrame
        baseline_stats: {metric: {mean, std, ...}} from reality_snapshot["numeric"]
        time_column:    time column name for temporal sorting
        valid_metrics:  allowlist of metric columns from DatasetProfiler.
                        If provided, any signal whose metric is NOT in this
                        list is rejected (blocks dimensions, identifiers, etc.)

    Returns:
        Filtered + annotated event list. Only signals that pass all checks survive.
        Each surviving signal carries a 'correctness' stamp.
    """
    if not events:
        return []

    # Build allowlist set for O(1) lookups
    metric_allowlist: set[str] | None = (
        set(valid_metrics) if valid_metrics else None
    )

    numeric_stats = baseline_stats if isinstance(baseline_stats, dict) else {}
    validated: list[dict[str, Any]] = []

    for event in events:
        metric = event.get("metric", "")

        # ── Step 0: Metric allowlist enforcement ─────────────────────
        if metric_allowlist is not None and metric not in metric_allowlist:
            log.info(f"[CORRECTNESS] Rejected non-metric column: {metric}")
            continue

        # ── Step 1: Column type enforcement ──────────────────────────
        if metric in df.columns:
            col_type = classify_column(metric, df[metric])
            if col_type == "identifier":
                log.info(f"[CORRECTNESS] Rejected identifier column: {metric}")
                continue

        # ── Step 2: Direction validation ─────────────────────────────
        validated_event = _validate_signal_direction(event, df, numeric_stats, time_column)
        if validated_event is None:
            log.info(
                f"[CORRECTNESS] Rejected signal: {metric} "
                f"direction={event.get('direction')} — failed validation"
            )
            continue

        # ── Step 3: Signed metric annotation ─────────────────────────
        if metric in df.columns:
            signed_ctx = compute_signed_metric_context(df[metric])
            if signed_ctx:
                validated_event = {**validated_event}
                validated_event["signed_metric"] = signed_ctx

        validated.append(validated_event)

    # ── Normalise direction to validated_direction ───────────────────
    # Ensures every consumer reading event["direction"] gets the
    # corrected value. validated_direction is retained as audit trail.
    final: list[dict[str, Any]] = []
    for e in validated:
        vdir = e.get("validated_direction")
        if vdir and e.get("direction") != vdir:
            e = {**e, "direction": vdir}
        final.append(e)

    # Sort for determinism (use corrected direction)
    final.sort(key=lambda e: (e.get("metric", ""), e.get("direction", "")))

    log.info(
        f"[CORRECTNESS] {len(events)} events → {len(final)} validated "
        f"({len(events) - len(final)} rejected)"
    )
    return final
