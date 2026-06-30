"""
aegis_ai/core/relative_intelligence.py
=========================================
Relative Intelligence Layer — cross-segment comparison for actionable insights.

Runs AFTER all core detection, independent of system_state.
Produces relative_decisions even when global decisions are empty
(NO_SIGNIFICANT_CHANGE) — the system can be stable overall but
still have meaningful segment-level variation.

This layer does NOT:
  - Detect temporal drift (that's BiasDetector)
  - Generate structural signals (that's DominanceDetector)
  - Modify existing decisions or silence behavior
  - Use ML or probabilistic models

This layer DOES:
  - Compare segment means against global means for key metrics
  - Apply economic polarity to generate directional actions
  - Adapt thresholds to metric variability (CV-based, deterministic)
  - Prioritize by deviation magnitude and metric importance
  - Suppress noise (< effective threshold, tiny segments)

Contract:
  - Deterministic: same df → same output
  - Fail-open: never blocks pipeline
  - Independent of system_state — but adapts sensitivity
  - Bounded: max _MAX_DECISIONS output
"""

from __future__ import annotations

import logging
import statistics
from typing import Any

import pandas as pd

log = logging.getLogger("aegis_ai.core.relative_intelligence")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — three-tier threshold system
# ─────────────────────────────────────────────────────────────────────────────

_NOISE_FLOOR          = 0.05   # 5% — absolute minimum, never generate below this
_LOW_DEVIATION        = 0.05   # 5% — LOW priority threshold (base, before CV adjustment)
_MEDIUM_DEVIATION     = 0.10   # 10% — MEDIUM priority threshold
_HIGH_DEVIATION       = 0.20   # 20% — HIGH priority threshold
_MIN_SEGMENT_SHARE    = 0.05   # segment must be ≥ 5% of total rows
_MIN_SEGMENT_ROWS     = 30     # absolute minimum rows
_MAX_DIMENSIONS       = 5
_MAX_DECISIONS        = 7      # allow more since we have 3 tiers now
_MAX_DIMENSION_UNIQUE = 50     # dimensions with > 50 values are likely IDs

# Global-vs-segment discriminator: if the CV of segment deviations
# for a (dimension, metric) pair is below this, it's a uniform global effect.
# CV-based (not absolute std) so it scales: 900%±50% std → CV=5.5% → uniform.
_UNIFORMITY_CV_THRESHOLD  = 0.30  # deviation CV < 30% → uniform
_UNIFORMITY_STD_THRESHOLD = 0.05  # absolute fallback for small deviations

# False opportunity filter: a segment whose deviation is within ±5pp
# of the average deviation is just riding the global wave — not a real outlier.
_FALSE_OPPORTUNITY_BAND   = 0.05  # ±5 percentage points

# Variance-aware threshold adjustment (deterministic, no ML)
# CV = std / |mean|.  High CV means the metric is noisy — raise the bar.
_CV_LOW_BOUND         = 0.15   # CV below this → stable metric, no adjustment
_CV_HIGH_BOUND        = 0.50   # CV above this → noisy metric, full adjustment
_CV_MAX_PENALTY       = 0.03   # max threshold increase for noisy metrics (3%)

# High-impact metrics get priority boost
_HIGH_IMPACT_KEYWORDS = frozenset([
    "revenue", "roi", "roas", "profit", "margin", "cost", "spend",
    "conversions", "churn", "cac", "clv", "ctr", "sales",
])


# ─────────────────────────────────────────────────────────────────────────────
# POLARITY — reuse the economic polarity inference from tradeoff_detector
# ─────────────────────────────────────────────────────────────────────────────

def _infer_polarity(metric_name: str) -> str:
    """
    Infer economic polarity. Reuses tradeoff_detector logic
    via import to maintain single source of truth.
    """
    try:
        from aegis_ai.company_brain.tradeoff_detector import _infer_polarity as _td_polarity
        return _td_polarity(metric_name)
    except ImportError:
        return "UNKNOWN"


def _is_high_impact(metric: str) -> bool:
    """Check if metric name contains high-impact keywords."""
    lower = metric.lower().replace("_", " ")
    return any(kw in lower for kw in _HIGH_IMPACT_KEYWORDS)


# ─────────────────────────────────────────────────────────────────────────────
# VARIANCE-AWARE THRESHOLD — deterministic CV-based adjustment
# ─────────────────────────────────────────────────────────────────────────────

def _cv_penalty(cv: float) -> float:
    """
    Compute threshold penalty based on coefficient of variation.

    Stable metric (CV < 0.15) → 0% penalty (trust small deviations)
    Noisy metric  (CV > 0.50) → +3% penalty (raise the bar)
    In between    → linear interpolation

    Deterministic, no ML, no dataset-specific logic.
    """
    if cv <= _CV_LOW_BOUND:
        return 0.0
    if cv >= _CV_HIGH_BOUND:
        return _CV_MAX_PENALTY
    # Linear interpolation between bounds
    ratio = (cv - _CV_LOW_BOUND) / (_CV_HIGH_BOUND - _CV_LOW_BOUND)
    return round(ratio * _CV_MAX_PENALTY, 4)


def _compute_metric_cv(
    metric: str,
    g_mean: float,
    numeric_stats: dict[str, Any] | None,
    df: pd.DataFrame,
) -> float:
    """
    Get coefficient of variation for a metric.
    Uses pre-computed stats if available, falls back to df computation.
    """
    # Try pre-computed stats first (from reality_snapshot)
    if numeric_stats and metric in numeric_stats:
        stats = numeric_stats[metric]
        std = abs(float(stats.get("std", 0.0)))
        mean = abs(float(stats.get("mean", g_mean)))
        if mean > 1e-9:
            return std / mean

    # Fallback: compute from df
    if metric in df.columns:
        std = float(df[metric].std())
        if abs(g_mean) > 1e-9:
            return abs(std / g_mean)

    return 0.25  # neutral default when unknown


# ─────────────────────────────────────────────────────────────────────────────
# ACTION GENERATION — polarity × deviation direction × priority → text
# ─────────────────────────────────────────────────────────────────────────────

def _generate_action(
    metric: str,
    segment_value: str,
    dimension: str,
    deviation: float,
    polarity: str,
    priority: str,
) -> tuple[str, str]:
    """
    Generate (insight_text, action_text) calibrated to priority level.

    Priority calibration:
      HIGH   → strong, actionable language
      MEDIUM → suggest optimization
      LOW    → monitoring / gradual adjustment
    """
    dev_pct = f"{abs(deviation) * 100:.1f}%"
    outperforming = deviation > 0

    # For GOOD_DOWN metrics, "outperforming" means LOWER (deviation < 0)
    if polarity == "GOOD_DOWN":
        outperforming = deviation < 0

    # ── Tone prefix by priority ──
    if priority == "HIGH":
        tone = "Significant"
    elif priority == "MEDIUM":
        tone = "Notable"
    else:
        tone = "Mild"

    # ── Insight text ──
    if polarity == "GOOD_UP":
        if outperforming:
            insight = f"{tone} outperformance: {metric} in {segment_value} ({dimension}) is {dev_pct} above average"
        else:
            insight = f"{tone} underperformance: {metric} in {segment_value} ({dimension}) is {dev_pct} below average"
    elif polarity == "GOOD_DOWN":
        if outperforming:
            insight = f"{tone} efficiency gain: {metric} in {segment_value} ({dimension}) is {dev_pct} below average"
        else:
            insight = f"{tone} cost pressure: {metric} in {segment_value} ({dimension}) is {dev_pct} above average"
    else:
        direction = "above" if deviation > 0 else "below"
        insight = f"{tone} variation: {metric} in {segment_value} ({dimension}) is {dev_pct} {direction} average"

    # ── Action text by priority ──
    if priority == "HIGH":
        if polarity == "GOOD_UP":
            action = (
                f"Scale investment in {segment_value} — {metric} is significantly above baseline."
                if outperforming else
                f"Investigate {metric} gap in {segment_value} — significant underperformance requires attention."
            )
        elif polarity == "GOOD_DOWN":
            action = (
                f"Replicate {segment_value} efficiency practices across other segments."
                if outperforming else
                f"Address {metric} pressure in {segment_value} — elevated cost is a structural risk."
            )
        else:
            action = f"Review {metric} in {segment_value} — significant deviation from baseline warrants investigation."

    elif priority == "MEDIUM":
        if polarity == "GOOD_UP":
            action = (
                f"Consider increasing allocation to {segment_value} — {metric} shows above-average returns."
                if outperforming else
                f"Evaluate {metric} efficiency in {segment_value} — below-average performance may be addressable."
            )
        elif polarity == "GOOD_DOWN":
            action = (
                f"Study {segment_value} for optimization patterns — {metric} is running leaner here."
                if outperforming else
                f"Monitor {metric} in {segment_value} — costs are trending above other segments."
            )
        else:
            action = f"Monitor {metric} in {segment_value} — deviation is notable but may stabilize."

    else:  # LOW
        if outperforming:
            action = f"Continue current approach in {segment_value} — {metric} is slightly ahead of baseline."
        else:
            action = f"Keep watching {metric} in {segment_value} — mild underperformance, no immediate action needed."

    return insight, action


# ─────────────────────────────────────────────────────────────────────────────
# PRIORITIZATION — three-tier with CV-adjusted effective threshold
# ─────────────────────────────────────────────────────────────────────────────

def _compute_priority(
    deviation: float,
    metric: str,
    effective_low_threshold: float,
) -> str:
    """
    Three-tier priority:
      HIGH   → abs(deviation) ≥ 20% AND high-impact metric (or ≥25% any metric)
      MEDIUM → abs(deviation) ≥ 10%
      LOW    → abs(deviation) ≥ effective_low_threshold (5% + CV penalty)
      (below LOW → suppressed)
    """
    abs_dev = abs(deviation)

    if abs_dev >= _HIGH_DEVIATION:
        if _is_high_impact(metric) or abs_dev >= 0.25:
            return "HIGH"
        return "MEDIUM"  # large deviation but not a key metric → MEDIUM

    if abs_dev >= _MEDIUM_DEVIATION:
        return "MEDIUM"

    if abs_dev >= effective_low_threshold:
        return "LOW"

    return "SUPPRESS"


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSION SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def _select_dimensions(df: pd.DataFrame, dimensions: list[str]) -> list[str]:
    """Pick dimensions with moderate cardinality. Sorted for determinism."""
    scored = []
    for dim in sorted(dimensions):
        if dim not in df.columns:
            continue
        n = df[dim].nunique()
        if n < 2 or n > _MAX_DIMENSION_UNIQUE:
            continue
        score = -abs(n - 15)
        scored.append((score, dim))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [dim for _, dim in scored[:_MAX_DIMENSIONS]]


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def compute_relative_decisions(
    df: pd.DataFrame,
    valid_metrics: list[str],
    dimensions: list[str],
    *,
    system_state: str = "",
    numeric_stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Compute segment-vs-global relative decisions for key metrics.

    Independent of system_state — produces insights even when the system
    is SILENT or NO_SIGNIFICANT_CHANGE. System state only affects the
    minimum priority tier included in output:
      - NO_SIGNIFICANT_CHANGE / SILENT → include LOW (≥5%, the system has
        nothing else to say, so surface subtle patterns)
      - INSIGHTFUL → include MEDIUM+ only (≥10%, avoid cluttering strong
        global decisions with minor segment noise)

    Args:
        df:             post-sanitisation DataFrame
        valid_metrics:  numeric metric columns from DatasetProfiler
        dimensions:     categorical dimension columns from DatasetProfiler
        system_state:   brain output state (INSIGHTFUL, SILENT, OBSERVATION, etc.)
        numeric_stats:  {metric: {mean, std, ...}} from reality_snapshot["numeric"]
                        Used for CV-based threshold adjustment. Optional.

    Returns:
        List of relative_decision dicts, sorted by priority then deviation.
        Empty if no segment exceeds the deviation + size thresholds.
    """
    if df.empty or not valid_metrics or not dimensions:
        return []

    total_rows = len(df)
    if total_rows < _MIN_SEGMENT_ROWS * 2:
        return []  # dataset too small for meaningful segmentation

    selected_dims = _select_dimensions(df, dimensions)
    if not selected_dims:
        return []

    # Select numeric metrics that exist in the dataframe
    metrics = [
        m for m in sorted(valid_metrics)
        if m in df.columns and pd.api.types.is_numeric_dtype(df[m])
    ]
    if not metrics:
        return []

    # Pre-compute global means
    global_means: dict[str, float] = {}
    for m in metrics:
        mean = float(df[m].mean())
        if abs(mean) > 1e-9:
            global_means[m] = mean

    if not global_means:
        return []

    # Pre-compute polarities and CV-adjusted thresholds per metric
    polarities: dict[str, str] = {}
    effective_thresholds: dict[str, float] = {}
    for m, g_mean in global_means.items():
        polarities[m] = _infer_polarity(m)
        cv = _compute_metric_cv(m, g_mean, numeric_stats, df)
        penalty = _cv_penalty(cv)
        effective_thresholds[m] = _LOW_DEVIATION + penalty

    # State-aware minimum priority:
    # When the system has nothing to say globally, surface more subtle
    # segment-level patterns. When global decisions exist, be stricter.
    has_global_signal = system_state in ("INSIGHTFUL",)
    min_priority = "MEDIUM" if has_global_signal else "LOW"
    _PRIO_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "SUPPRESS": 9}
    min_rank = _PRIO_RANK[min_priority]

    candidates: list[dict[str, Any]] = []

    # ── Phase 1: Collect ALL segment deviations per (dim, metric) ─────
    # Structure: {(dim, metric): [(val_str, seg_mean, deviation, seg_share), ...]}
    dim_metric_deviations: dict[tuple[str, str], list[tuple[str, float, float, float]]] = {}

    for dim in selected_dims:
        try:
            groups = df.groupby(dim, sort=True)
        except Exception:
            continue

        for value, group_df in groups:
            seg_rows = len(group_df)
            seg_share = seg_rows / total_rows

            # Size gates — strict, never relaxed
            if seg_rows < _MIN_SEGMENT_ROWS:
                continue
            if seg_share < _MIN_SEGMENT_SHARE:
                continue

            val_str = str(value).strip()
            if not val_str or val_str.lower() in ("nan", "none", ""):
                continue

            for metric, g_mean in global_means.items():
                if metric not in group_df.columns:
                    continue

                seg_mean = float(group_df[metric].mean())
                deviation = (seg_mean - g_mean) / abs(g_mean)

                key = (dim, metric)
                if key not in dim_metric_deviations:
                    dim_metric_deviations[key] = []
                dim_metric_deviations[key].append(
                    (val_str, seg_mean, deviation, seg_share)
                )

    # ── Phase 2: Detect global effects vs segment-specific patterns ───
    # For each (dim, metric), check if segments deviate uniformly.
    # If so, it's a global effect — emit 1 insight, not N.
    # Uses BOTH CV-based and absolute-std checks (whichever is more permissive)
    # and majority-same-sign (≥75%) instead of strict all-same-sign.
    global_effects: set[tuple[str, str]] = set()   # (dim, metric) pairs
    global_effect_metrics: set[str] = set()        # metrics with global effect on ANY dim
    uniformity_metrics: set[str] = set()           # metrics with uniform-but-tiny behavior
    dim_metric_avg_dev: dict[tuple[str, str], float] = {}  # for false-opportunity filter

    for (dim, metric), entries in sorted(dim_metric_deviations.items()):
        if len(entries) < 2:
            continue

        deviations = [e[2] for e in entries]
        dev_std = statistics.pstdev(deviations)  # population std — deterministic
        dev_mean = statistics.mean(deviations)
        dim_metric_avg_dev[(dim, metric)] = dev_mean

        # Majority-same-sign: ≥75% of segments in the same direction.
        # Handles the case where 4/5 segments are positive and 1 is -0.1%.
        n_positive = sum(1 for d in deviations if d > 0)
        n_negative = sum(1 for d in deviations if d < 0)
        n_total = len(deviations)
        majority_same_sign = (n_positive / n_total >= 0.75) or (n_negative / n_total >= 0.75)

        # Uniformity check: CV-based (scales with magnitude) OR absolute-std (for small deviations)
        dev_cv = dev_std / abs(dev_mean) if abs(dev_mean) > 1e-9 else 999.0
        is_uniform = (
            (dev_cv < _UNIFORMITY_CV_THRESHOLD or dev_std < _UNIFORMITY_STD_THRESHOLD)
            and majority_same_sign
            and abs(dev_mean) >= _NOISE_FLOOR
        )

        if is_uniform:
            global_effects.add((dim, metric))
            global_effect_metrics.add(metric)
            direction = "increase" if dev_mean > 0 else "decrease"
            avg_dev_pct = f"{abs(dev_mean) * 100:.1f}%"

            # Assign priority — global effects with >30% magnitude get HIGH
            priority = _compute_priority(dev_mean, metric, effective_thresholds.get(metric, _LOW_DEVIATION))
            if priority == "SUPPRESS":
                priority = "LOW"  # global effects are always worth mentioning
            if abs(dev_mean) > 0.30:
                priority = "HIGH"

            if _PRIO_RANK.get(priority, 9) <= min_rank:
                candidates.append({
                    "type":       "GLOBAL_EFFECT",
                    "metric":     metric,
                    "dimension":  dim,
                    "segment":    f"all {dim} segments",
                    "deviation":  round(dev_mean, 4),
                    "segment_mean": 0.0,
                    "global_mean": round(global_means[metric], 4),
                    "segment_share": 1.0,
                    "polarity":   polarities.get(metric, "UNKNOWN"),
                    "insight": (
                        f"{metric} {direction} (~{avg_dev_pct}) is consistent across all {dim} "
                        f"segments, indicating a system-wide shift rather than segment-specific behavior."
                    ),
                    "action": (
                        f"This is a system-wide movement in {metric} — investigate macro-level drivers "
                        f"rather than individual {dim} segments."
                    ),
                    "priority":   priority,
                })
        elif majority_same_sign and all(abs(d) < _NOISE_FLOOR for d in deviations):
            uniformity_metrics.add(metric)

    # ── Phase 3: Generate segment-specific decisions (non-uniform only) ──
    # Two suppression rules:
    #   a) Skip (dim, metric) pairs flagged as global effects
    #   b) Skip metrics flagged as global on ANY dimension (cross-dim suppression)
    #   c) False-opportunity filter: skip segments whose deviation is within
    #      ±5pp of the average deviation (riding the global wave, not truly different)
    for (dim, metric), entries in sorted(dim_metric_deviations.items()):
        if (dim, metric) in global_effects:
            continue  # already emitted as global effect
        if metric in global_effect_metrics:
            continue  # metric is global on another dimension — suppress here too

        g_mean = global_means[metric]
        avg_dev = dim_metric_avg_dev.get((dim, metric), 0.0)

        for val_str, seg_mean, deviation, seg_share in entries:
            # Hard noise floor
            if abs(deviation) < _NOISE_FLOOR:
                continue

            # False-opportunity filter: if this segment's deviation is within
            # ±5pp of the average deviation for this (dim, metric), it's just
            # riding the global wave — not a real outlier.
            if abs(deviation - avg_dev) < _FALSE_OPPORTUNITY_BAND:
                continue

            eff_threshold = effective_thresholds.get(metric, _LOW_DEVIATION)
            priority = _compute_priority(deviation, metric, eff_threshold)

            if priority == "SUPPRESS":
                continue
            if _PRIO_RANK[priority] > min_rank:
                continue

            polarity = polarities.get(metric, "UNKNOWN")
            insight, action = _generate_action(
                metric, val_str, dim, deviation, polarity, priority,
            )

            is_outperforming = deviation > 0
            if polarity == "GOOD_DOWN":
                is_outperforming = deviation < 0

            decision_type = (
                "SEGMENT_OPPORTUNITY" if is_outperforming
                else "SEGMENT_RISK"
            )

            candidates.append({
                "type":       decision_type,
                "metric":     metric,
                "dimension":  dim,
                "segment":    val_str,
                "deviation":  round(deviation, 4),
                "segment_mean": round(seg_mean, 4),
                "global_mean": round(g_mean, 4),
                "segment_share": round(seg_share, 4),
                "polarity":   polarity,
                "insight":    insight,
                "action":     action,
                "priority":   priority,
            })

    # ── Phase 4: Uniformity fallback ─────────────────────────────────
    # If no candidates were generated but segments are consistent,
    # emit a single uniformity insight so the output isn't empty.
    if not candidates and uniformity_metrics:
        metric_list = ", ".join(sorted(uniformity_metrics)[:3])
        candidates.append({
            "type":       "UNIFORM_PERFORMANCE",
            "metric":     metric_list,
            "dimension":  ", ".join(selected_dims[:2]),
            "segment":    "all segments",
            "deviation":  0.0,
            "segment_mean": 0.0,
            "global_mean": 0.0,
            "segment_share": 1.0,
            "polarity":   "NEUTRAL",
            "insight": (
                f"Performance is consistent across all segments with no significant "
                f"differentiation in {metric_list}."
            ),
            "action": (
                "No segment-specific action needed — behavior is uniform across the dataset."
            ),
            "priority":   "LOW",
        })

    if not candidates:
        return []

    # Sort: HIGH first, then MEDIUM, then LOW;
    # within tier: abs(deviation) desc; metric+segment for determinism
    candidates.sort(key=lambda c: (
        _PRIO_RANK.get(c["priority"], 9),
        -abs(c["deviation"]),
        c["metric"],
        c.get("segment", ""),
    ))

    return candidates[:_MAX_DECISIONS]
