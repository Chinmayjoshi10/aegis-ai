"""
aegis_ai/core/segment_engine.py
==================================
Segment Engine — contextual metric decomposition by dimension.

Segments are NOT independent signals.
Segments compare validated metric behavior within dimension slices
against global metric behavior.

Output:
{
  "Country=United Kingdom": [
    {
      "metric": "Price",
      "global_direction": "DOWNWARD",
      "segment_mean": 12.50,
      "global_mean": 12.66,
      "deviation": -0.013,
      "summary": "Price is DOWNWARD globally, but in United Kingdom it is lower than global"
    }
  ]
}

Contract:
  - Segments explain metrics, never generate independent trends
  - Only validated_metrics can appear in segment output
  - Dimensions are slicers, not signals
  - Deterministic: sorted dimensions and segments
  - Fail-open: one broken segment never blocks others
"""

from __future__ import annotations

import logging
import statistics
from typing import Any

import pandas as pd

log = logging.getLogger("aegis_ai.core.segment_engine")

_MAX_DIMENSIONS     = 5
_MAX_SEGMENTS       = 5
_MIN_SEGMENT_ROWS   = 50
_MAX_SEGMENT_LABEL_LEN = 40

# Global-effect detection: if the coefficient of variation of segment
# deviations for a metric within a dimension is below this, the movement
# is uniform → global effect, not segment-specific.
_UNIFORMITY_CV_THRESHOLD = 0.30  # deviation CV < 30% → uniform

# F-13: Aligned with generate_segment_decisions threshold (was 0.2, decisions used 0.05).
# Using 0.10 as compromise — segments with >=10% deviation are attached to signals.
_DEVIATION_THRESHOLD = 0.10
_MAX_SEGMENTS_PER_SIGNAL = 3


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL ENRICHMENT — attach WHERE context to existing signals
# ─────────────────────────────────────────────────────────────────────────────

def enrich_signals_with_segments(
    insights: list[dict[str, Any]],
    df: pd.DataFrame,
    dimensions: list[str],
    valid_metrics: list[str],
    *,
    min_rows: int = _MIN_SEGMENT_ROWS,
    deviation_threshold: float = _DEVIATION_THRESHOLD,
    max_dimensions: int = _MAX_DIMENSIONS,
) -> list[dict[str, Any]]:
    """
    Enrich existing brain signals with segment-level context.

    For each signal, identifies which categorical segments deviate
    most from the global mean for that signal's metric. Attaches
    segment metadata directly to the signal — no new signal types.

    Args:
        insights:            raw insights from run_company_brain_v2()
        df:                  mapped dataframe (post-semantic-mapping)
        dimensions:          categorical columns from profiler
        valid_metrics:       numeric metric columns from profiler
        min_rows:            minimum rows for a segment to qualify
        deviation_threshold: abs(deviation) must exceed this to attach

    Returns:
        Same insights list, each insight potentially enriched with
        a "segment_context" key containing top deviating segments.
    """
    if not insights or df.empty or not dimensions:
        return insights

    usable_dims = [d for d in sorted(dimensions) if d in df.columns][:max_dimensions]
    if not usable_dims:
        return insights

    # Pre-compute global means for all valid metrics (deterministic)
    global_means: dict[str, float] = {}
    for m in sorted(valid_metrics):
        if m in df.columns and pd.api.types.is_numeric_dtype(df[m]):
            mean = float(df[m].mean())
            if abs(mean) > 1e-9:
                global_means[m] = mean

    # Pre-compute segment deviations per (dimension, metric)
    # Structure: {metric: [(dimension, value, deviation, count), ...]}
    segment_cache: dict[str, list[tuple[str, str, float, int]]] = {}

    for dim in usable_dims:
        try:
            groups = df.groupby(dim, sort=True)
            for value, group_df in groups:
                if len(group_df) < min_rows:
                    continue
                val_str = str(value).strip()
                if not val_str or val_str.lower() in ("nan", "none", ""):
                    continue

                for metric, g_mean in global_means.items():
                    if metric not in group_df.columns:
                        continue
                    seg_mean = float(group_df[metric].mean())
                    deviation = (seg_mean - g_mean) / g_mean

                    if abs(deviation) >= deviation_threshold:
                        if metric not in segment_cache:
                            segment_cache[metric] = []
                        segment_cache[metric].append(
                            (dim, val_str, round(deviation, 4), len(group_df))
                        )
        except Exception as e:
            log.warning(f"[SEGMENT_ENGINE] Enrichment failed for dim={dim}: {e}")
            continue

    # Sort each metric's segments by abs(deviation) desc, dim+value for determinism
    for metric in segment_cache:
        segment_cache[metric].sort(
            key=lambda x: (-abs(x[2]), x[0], x[1])
        )

    # Enrich each insight
    enriched: list[dict[str, Any]] = []
    for insight in insights:
        insight = {**insight}  # shallow copy — don't mutate originals

        # Determine the metric(s) this insight refers to
        primitive = insight.get("primitive", "")
        if primitive == "TRADEOFF":
            metrics = insight.get("metrics") or []
        else:
            m = insight.get("metric")
            metrics = [m] if m else []

        # Collect segment context for this insight's metrics
        segments_for_signal: list[dict[str, Any]] = []
        for metric in metrics:
            if metric not in segment_cache:
                continue
            for dim, value, deviation, count in segment_cache[metric][:_MAX_SEGMENTS_PER_SIGNAL]:
                segments_for_signal.append({
                    "dimension": dim,
                    "value": value,
                    "metric": metric,
                    "deviation": deviation,
                    "segment_rows": count,
                })

        # Sort and limit
        segments_for_signal.sort(
            key=lambda s: (-abs(s["deviation"]), s["dimension"], str(s["value"]))
        )
        segments_for_signal = segments_for_signal[:_MAX_SEGMENTS_PER_SIGNAL]

        if segments_for_signal:
            insight["segment_context"] = segments_for_signal

        enriched.append(insight)

    return enriched


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API — contextual segment decomposition
# ─────────────────────────────────────────────────────────────────────────────

def generate_segment_decisions(
    df: pd.DataFrame,
    dimensions: list[str],
    baseline_stats: dict[str, Any],
    global_decisions: list[dict[str, Any]],
    data_understanding: dict[str, Any] | None = None,
    *,
    ordered_data: bool = False,
    min_rows: int = _MIN_SEGMENT_ROWS,
    valid_metrics: list[str] | None = None,
    validated_signals: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Generate per-segment context for validated metrics across dimensions.

    This does NOT run independent signal detection per segment.
    Instead, for each validated metric signal, it compares segment-level
    means against the global mean to explain WHERE the metric behavior
    is concentrated.

    Args:
        df:                 cleaned dataframe (post-sanitization)
        dimensions:         categorical column names from DatasetProfiler
        baseline_stats:     {"metric": {mean, std, ...}} from RealityReader
        global_decisions:   already-computed global decisions
        ordered_data:       (unused — kept for API compat)
        min_rows:           minimum rows for a segment to qualify
        valid_metrics:      allowlist of metric columns
        validated_signals:  validated events from correctness_layer

    Returns:
        {"DIMENSION=value": [segment_contexts], ...}
    """
    important_dimensions = (
        data_understanding.get("important_dimensions", [])
        if data_understanding
        else []
    )
    dimensions = important_dimensions or dimensions

    if df.empty or not dimensions:
        return {}

    # Determine which metrics have validated signals
    signaled_metrics: dict[str, str] = {}  # metric → validated_direction
    if validated_signals:
        for sig in validated_signals:
            m = sig.get("metric", "")
            vdir = sig.get("validated_direction", sig.get("direction", ""))
            if m and vdir:
                signaled_metrics[m] = vdir

    if not signaled_metrics:
        return {}

    # Filter to valid_metrics only
    if valid_metrics:
        allowed = set(valid_metrics)
        signaled_metrics = {m: d for m, d in signaled_metrics.items() if m in allowed}

    if not signaled_metrics:
        return {}

    # Compute global means for signaled metrics
    global_means: dict[str, float] = {}
    for m in signaled_metrics:
        if m in df.columns and pd.api.types.is_numeric_dtype(df[m]):
            mean_val = float(df[m].mean())
            if abs(mean_val) > 1e-9:
                global_means[m] = mean_val

    if not global_means:
        return {}

    # Select dimensions
    selected_dims = _select_dimensions(df, dimensions)

    segment_output: dict[str, list] = {}

    for dim in selected_dims:
        if dim not in df.columns:
            continue

        try:
            value_counts = df[dim].value_counts()
            top_values = (
                value_counts[value_counts >= min_rows]
                .head(_MAX_SEGMENTS)
                .index
                .tolist()
            )

            for value in top_values:
                segment_df = df[df[dim] == value]
                if len(segment_df) < min_rows:
                    continue

                label = _make_label(dim, value)
                contexts: list[dict[str, Any]] = []

                for metric, global_dir in signaled_metrics.items():
                    if metric not in segment_df.columns:
                        continue
                    if metric not in global_means:
                        continue

                    s_len = len(segment_df)
                    if ordered_data and s_len >= 10:
                        early_mean = float(segment_df[metric].iloc[:s_len // 2].mean())
                        late_mean = float(segment_df[metric].iloc[s_len // 2:].mean())
                        if abs(early_mean) < 1e-9:
                            continue
                        deviation = (late_mean - early_mean) / abs(early_mean)
                    else:
                        seg_mean = float(segment_df[metric].mean())
                        glob_mean = global_means[metric]
                        if abs(glob_mean) < 1e-9:
                            continue
                        deviation = (seg_mean - glob_mean) / abs(glob_mean)
                        early_mean = glob_mean
                        late_mean = seg_mean

                    if abs(deviation) <= 0.05:
                        continue

                    position = (
                        "trending higher"
                        if deviation > 0.01 else "trending lower"
                    ) if ordered_data else (
                        "higher than global averages" 
                        if deviation > 0.01 else "lower than global averages"
                    )

                    contexts.append({
                        "type": "SEGMENT_CONTEXT",
                        "metric": metric,
                        "global_direction": global_dir,
                        "significant": abs(deviation) > 0.1,
                        "segment_mean": round(late_mean, 4),
                        "global_mean": round(early_mean, 4),
                        "deviation": round(deviation, 4),
                        "dimension": dim,
                        "segment_value": str(value),
                        "segment_rows": len(segment_df),
                        "summary": (
                            f"{metric} in {value} moved from {early_mean:.2f} "
                            f"to {late_mean:.2f} ({deviation:+.1%})"
                        ),
                        "fact": f"{metric} is {position} in {value}.",
                        "pattern": f"In {value} ({dim}), {metric} is {position}.",
                        "impact": (
                            f"This segment accounts for "
                            f"{len(segment_df)/len(df)*100:.1f}% of the data."
                        ),
                        "action": (
                            f"Investigate {value} for {metric} anomalies."
                            if abs(deviation) >= 0.1
                            else f"No action needed — {value} is aligned with global trend."
                        ),
                    })

                # Filter: only keep meaningful segments
                # deviation >= 5% OR segment share >= 5%
                segment_share = len(segment_df) / len(df)
                meaningful = [
                    c for c in contexts
                    if abs(c["deviation"]) >= 0.05 or segment_share >= 0.05
                ]

                if meaningful:
                    # Sort by abs(deviation) desc for determinism
                    meaningful.sort(
                        key=lambda c: (-abs(c["deviation"]), c["metric"])
                    )
                    segment_output[label] = meaningful

        except Exception as e:
            log.error(f"[SEGMENT_ENGINE] Dimension '{dim}' failed: {e}", exc_info=True)
            continue

    # ── Global-effect post-processing ────────────────────────────────
    # If ALL segments for a (dimension, metric) show similar deviation,
    # the movement is global — not segment-specific. Replace N segment
    # entries with 1 global-effect entry to prevent segment spam.
    segment_output = _suppress_uniform_segments(segment_output)

    return segment_output


def _suppress_uniform_segments(
    segment_output: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Post-process segment output to detect and suppress global effects.

    Groups contexts by (dimension, metric). If the coefficient of variation
    of deviations across segments is below threshold AND all deviations have
    the same sign, the movement is uniform — replace N entries with 1 global.
    """
    if not segment_output:
        return segment_output

    # ── Step 1: Group all contexts by (dimension_name, metric) ────────
    # Extract dimension name from label ("Market_Region=SAARC" → "Market_Region")
    dim_metric_entries: dict[tuple[str, str], list[tuple[str, dict]]] = {}

    for label, contexts in segment_output.items():
        dim_name = label.split("=")[0] if "=" in label else label
        for ctx in contexts:
            metric = ctx.get("metric", "")
            key = (dim_name, metric)
            if key not in dim_metric_entries:
                dim_metric_entries[key] = []
            dim_metric_entries[key].append((label, ctx))

    # ── Step 2: Detect uniform metrics ────────────────────────────────
    uniform_dim_metrics: set[tuple[str, str]] = set()
    global_summaries: dict[tuple[str, str], dict] = {}

    for (dim_name, metric), entries in sorted(dim_metric_entries.items()):
        if len(entries) < 2:
            continue

        deviations = [ctx.get("deviation", 0.0) for _, ctx in entries]

        # Check same sign (all positive or all negative)
        all_same_sign = all(d > 0 for d in deviations) or all(d < 0 for d in deviations)
        if not all_same_sign:
            continue

        dev_mean = statistics.mean(deviations)
        if abs(dev_mean) < 0.01:
            continue  # too small to be interesting

        dev_std = statistics.pstdev(deviations)
        # Use coefficient of variation of deviations to detect uniformity.
        # If all segments deviate by ~900%, std might be 50% but CV = 50/900 = 0.055.
        dev_cv = dev_std / abs(dev_mean) if abs(dev_mean) > 1e-9 else 999.0

        if dev_cv < _UNIFORMITY_CV_THRESHOLD:
            uniform_dim_metrics.add((dim_name, metric))
            direction = "increase" if dev_mean > 0 else "decrease"
            avg_pct = f"{abs(dev_mean) * 100:.0f}%"
            global_dir = entries[0][1].get("global_direction", "")

            global_summaries[(dim_name, metric)] = {
                "type": "SEGMENT_CONTEXT",
                "metric": metric,
                "global_direction": global_dir,
                "significant": True,
                "segment_mean": 0.0,
                "global_mean": entries[0][1].get("global_mean", 0.0),
                "deviation": round(dev_mean, 4),
                "dimension": dim_name,
                "segment_value": f"all {dim_name} segments",
                "segment_rows": 0,
                "summary": (
                    f"{metric} {direction} (~{avg_pct}) is uniform across all "
                    f"{dim_name} segments — this is a system-wide shift."
                ),
                "fact": f"{metric} is {direction.rstrip('e')}ing uniformly across all {dim_name} segments.",
                "pattern": (
                    f"All {dim_name} segments show similar {metric} {direction} "
                    f"(~{avg_pct}), indicating a global effect rather than "
                    f"segment-specific behavior."
                ),
                "impact": "This is a system-wide movement — segment-level investigation is not productive.",
                "action": (
                    f"Investigate macro-level drivers of {metric} {direction} "
                    f"rather than individual {dim_name} segments."
                ),
            }

    if not uniform_dim_metrics:
        return segment_output

    # ── Step 3: Rebuild output — suppress uniform, add global entries ──
    new_output: dict[str, list] = {}

    for label, contexts in segment_output.items():
        dim_name = label.split("=")[0] if "=" in label else label
        filtered = [
            ctx for ctx in contexts
            if (dim_name, ctx.get("metric", "")) not in uniform_dim_metrics
        ]
        if filtered:
            new_output[label] = filtered

    # Add one global entry per uniform (dim, metric)
    for (dim_name, metric), summary in sorted(global_summaries.items()):
        global_label = f"{dim_name}=GLOBAL_EFFECT"
        if global_label not in new_output:
            new_output[global_label] = []
        new_output[global_label].append(summary)

    return new_output


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSION SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def _select_dimensions(df: pd.DataFrame, dimensions: list[str]) -> list[str]:
    """
    Pick up to _MAX_DIMENSIONS dimensions, preferring those with
    moderate cardinality (3–50 unique values) — too few = no signal,
    too many = no useful segmentation.

    Returns sorted list for determinism.
    """
    scored = []
    for dim in dimensions:
        if dim not in df.columns:
            continue
        n_unique = df[dim].nunique()
        # Ideal cardinality: 3–50 unique values
        if n_unique < 2 or n_unique > 200:
            continue
        # Score: penalise extremes, reward moderate cardinality
        score = -abs(n_unique - 15)   # peak at 15 unique values
        scored.append((score, dim))

    scored.sort(key=lambda x: (-x[0], x[1]))   # sort by score desc, name asc (deterministic)
    return [dim for _, dim in scored[:_MAX_DIMENSIONS]]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_label(dim: str, value: Any) -> str:
    """
    Create a readable, safe segment label.
    Truncates long values to avoid unreadable keys.
    """
    val_str = str(value).strip()
    if len(val_str) > _MAX_SEGMENT_LABEL_LEN:
        val_str = val_str[:_MAX_SEGMENT_LABEL_LEN] + "…"
    return f"{dim}={val_str}"
