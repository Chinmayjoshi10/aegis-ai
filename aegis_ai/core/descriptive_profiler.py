"""
aegis_ai/core/descriptive_profiler.py
========================================
Descriptive Intelligence Layer — unconditional, domain-agnostic.

Produces exploratory insights from ANY tabular dataset using only
aggregation and threshold logic. Does not depend on signals, baselines,
temporal structure, or domain parameters.

Runs on every upload. Guarantees non-empty output whenever the dataset
has at least one metric column and one dimension column.

Computations:
  1. Concentration Index  — HHI + top-N share per (dimension, metric)
  2. Ranked Performance   — top-5 / bottom-5 segments per (dimension, metric)
  3. Distribution Anomaly — negatives, extremes, high-zero in each metric
  4. Variance Decomposition — how much of a metric's variance each dimension explains

Contract:
  - Deterministic: same df → same output
  - Fail-open: one failed computation never blocks others
  - Domain-agnostic: no column names, no domain strings in logic
  - Bounded: max 5 dimensions × 10 metrics = 50 pairs, <2s for 1M rows
  - No ML, no LLM, no signals required
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import numpy as np

log = logging.getLogger("aegis_ai.core.descriptive_profiler")

# ─────────────────────────────────────────────────────────────────────────────
# BOUNDS
# ─────────────────────────────────────────────────────────────────────────────

_MAX_DIMENSIONS        = 5
_MAX_METRICS           = 10
_MAX_SEGMENTS_RANKED   = 5      # top-N and bottom-N
_MAX_INSIGHTS          = 30
_MIN_SEGMENT_ROWS      = 30
_MIN_DIMENSION_UNIQUE  = 2
_MAX_DIMENSION_UNIQUE  = 200    # above this it's likely free text / IDs


# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

_CONCENTRATION_TOP1_HIGH   = 0.70
_CONCENTRATION_TOP1_MEDIUM = 0.50
_CONCENTRATION_TOP3_HIGH   = 0.80
_HHI_THRESHOLD             = 0.25

_VARIANCE_EXPLAINED_MIN    = 0.10   # dimension must explain >10% of metric var

_NEGATIVE_MIN_POSITIVE_PCT = 0.90   # metric must be ≥90% positive to flag negatives
_EXTREME_QUANTILE          = 0.999
_ZERO_RATIO_THRESHOLD      = 0.50


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSION SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def _select_dimensions(
    df: pd.DataFrame,
    dimensions: list[str],
) -> list[str]:
    """
    Pick the most informative dimensions — moderate cardinality preferred.
    Returns sorted list for determinism.
    """
    scored = []
    for dim in sorted(dimensions):
        if dim not in df.columns:
            continue
        n = df[dim].nunique()
        if n < _MIN_DIMENSION_UNIQUE or n > _MAX_DIMENSION_UNIQUE:
            continue
        # Peak score at ~15 unique values — penalise extremes
        score = -abs(n - 15)
        scored.append((score, dim))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [dim for _, dim in scored[:_MAX_DIMENSIONS]]


def _select_metrics(
    df: pd.DataFrame,
    valid_metrics: list[str],
) -> list[str]:
    """Pick up to _MAX_METRICS numeric columns, sorted by name for determinism."""
    usable = [m for m in sorted(valid_metrics) if m in df.columns
              and pd.api.types.is_numeric_dtype(df[m])]
    return usable[:_MAX_METRICS]


# ─────────────────────────────────────────────────────────────────────────────
# COMPUTATION 1: CONCENTRATION INDEX
# ─────────────────────────────────────────────────────────────────────────────

def _concentration_insights(
    df: pd.DataFrame,
    dim: str,
    metric: str,
) -> list[dict[str, Any]]:
    """Compute concentration of metric across dimension values."""
    insights: list[dict] = []

    try:
        grouped = df.groupby(dim)[metric].sum()
        total = grouped.sum()
        if total == 0 or pd.isna(total):
            return []

        shares = (grouped / total).sort_values(ascending=False)
        n_segments = len(shares)
        top1_val = shares.index[0]
        top1_share = float(shares.iloc[0])
        top3_share = float(shares.iloc[:3].sum()) if len(shares) >= 3 else top1_share
        hhi = float((shares ** 2).sum())

        # Guard: near-uniform distributions are not concentration.
        # Uniform HHI = 1/n.  If actual HHI ≤ 1.5× uniform, the spread
        # is approximately even — flagging it would be a false positive.
        if n_segments >= 2:
            uniform_hhi = 1.0 / n_segments
            if hhi <= 1.5 * uniform_hhi:
                return []   # distribution is approximately even

        # Determine severity
        if top1_share >= _CONCENTRATION_TOP1_HIGH:
            severity = "HIGH"
        elif top1_share >= _CONCENTRATION_TOP1_MEDIUM:
            severity = "MEDIUM"
        elif hhi >= _HHI_THRESHOLD:
            severity = "MEDIUM"
        else:
            return []   # no significant concentration

        top1_pct = round(top1_share * 100, 1)
        insights.append({
            "type": "CONCENTRATION",
            "dimension": dim,
            "metric": metric,
            "severity": severity,
            "summary": (
                f"A single value of {dim} ('{top1_val}') accounts for "
                f"{top1_pct}% of total {metric}. "
                + ("This represents extreme concentration risk. " if severity == "HIGH"
                   else "This represents significant concentration. ")
                + f"Top 3 segments account for {round(top3_share * 100, 1)}%."
            ),
            "evidence": {
                "top_segment": str(top1_val),
                "top_share": round(top1_share, 4),
                "top3_share": round(top3_share, 4),
                "hhi": round(hhi, 4),
                "total_segments": len(shares),
            },
        })
    except Exception as e:
        log.debug(f"[DESCRIPTIVE] concentration failed dim={dim} metric={metric}: {e}")

    return insights


# ─────────────────────────────────────────────────────────────────────────────
# COMPUTATION 2: RANKED PERFORMANCE
# ─────────────────────────────────────────────────────────────────────────────

def _ranked_insights(
    df: pd.DataFrame,
    dim: str,
    metric: str,
) -> list[dict[str, Any]]:
    """Top-N and bottom-N segments by aggregated metric."""
    insights: list[dict] = []

    try:
        agg = df.groupby(dim)[metric].agg(["sum", "mean", "count"])
        # Only include segments with enough rows
        agg = agg[agg["count"] >= _MIN_SEGMENT_ROWS]
        if len(agg) < 2:
            return []

        agg = agg.sort_values("sum", ascending=False)

        top = agg.head(_MAX_SEGMENTS_RANKED)
        bottom = agg.tail(_MAX_SEGMENTS_RANKED)

        total = agg["sum"].sum()
        top_share = float(top["sum"].sum() / total) if total != 0 else 0.0

        top_segments = [
            {"value": str(idx), "total": round(float(row["sum"]), 2),
             "mean": round(float(row["mean"]), 2), "count": int(row["count"])}
            for idx, row in top.iterrows()
        ]
        bottom_segments = [
            {"value": str(idx), "total": round(float(row["sum"]), 2),
             "mean": round(float(row["mean"]), 2), "count": int(row["count"])}
            for idx, row in bottom.iterrows()
        ]

        insights.append({
            "type": "TOP_PERFORMERS",
            "dimension": dim,
            "metric": metric,
            "severity": "INFO",
            "summary": (
                f"Top {len(top_segments)} segments of {dim} by {metric}: "
                f"{', '.join(s['value'] for s in top_segments[:3])}. "
                f"Together they account for {round(top_share * 100, 1)}% of total {metric}."
            ),
            "evidence": {
                "top_segments": top_segments,
                "bottom_segments": bottom_segments,
                "total_qualifying_segments": len(agg),
                "top_share": round(top_share, 4),
            },
        })

        # Only emit bottom performers if there are negatives or meaningful spread
        if len(agg) >= 5:
            insights.append({
                "type": "BOTTOM_PERFORMERS",
                "dimension": dim,
                "metric": metric,
                "severity": "LOW" if bottom["sum"].min() >= 0 else "MEDIUM",
                "summary": (
                    f"Bottom {len(bottom_segments)} segments of {dim} by {metric}: "
                    f"{', '.join(s['value'] for s in bottom_segments[:3])}."
                ),
                "evidence": {
                    "bottom_segments": bottom_segments,
                },
            })

    except Exception as e:
        log.debug(f"[DESCRIPTIVE] ranked failed dim={dim} metric={metric}: {e}")

    return insights


# ─────────────────────────────────────────────────────────────────────────────
# COMPUTATION 3: DISTRIBUTION ANOMALIES
# ─────────────────────────────────────────────────────────────────────────────

def _anomaly_insights(
    df: pd.DataFrame,
    metric: str,
    dimensions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Detect structurally anomalous values: negatives, extremes, high-zero."""
    insights: list[dict] = []

    try:
        s = df[metric].dropna()
        if len(s) == 0:
            return []

        n_total = len(s)
        n_positive = int((s > 0).sum())
        n_negative = int((s < 0).sum())
        n_zero = int((s == 0).sum())
        positive_pct = n_positive / n_total if n_total > 0 else 0

        # Negative values in a predominantly positive metric
        if n_negative > 0 and positive_pct >= _NEGATIVE_MIN_POSITIVE_PCT:
            negative_sum = float(s[s < 0].sum())

            # Segment attribution: find which dimension/segment has the most negatives
            top_segment = None
            if dimensions and n_negative >= 1:
                try:
                    neg_mask = df[metric] < 0
                    best_dim, best_val, best_count = None, None, 0
                    for dim in (dimensions or []):
                        if dim not in df.columns:
                            continue
                        grouped = df.loc[neg_mask].groupby(dim).size()
                        if grouped.empty:
                            continue
                        top_val = grouped.idxmax()
                        top_cnt = int(grouped.max())
                        if top_cnt > best_count:
                            best_dim, best_val, best_count = dim, str(top_val), top_cnt
                    if best_dim and best_count > 0:
                        top_segment = {
                            "dimension": best_dim,
                            "value": best_val,
                            "count": best_count,
                            "share_pct": round(best_count / max(n_negative, 1) * 100, 1),
                        }
                except Exception:
                    pass

            evidence = {
                "negative_count": n_negative,
                "negative_total": round(negative_sum, 2),
                "positive_pct": round(positive_pct, 4),
                "total_rows": n_total,
            }
            if top_segment:
                evidence["top_segment"] = top_segment

            seg_phrase = ""
            if top_segment:
                seg_phrase = f" concentrated in {top_segment['value']}"

            insights.append({
                "type": "ANOMALY",
                "dimension": None,
                "metric": metric,
                "severity": "HIGH" if n_negative > n_total * 0.01 else "MEDIUM",
                "summary": (
                    f"{n_negative:,} rows have negative {metric} values "
                    f"(total: {negative_sum:,.2f}). {round(positive_pct * 100, 1)}% "
                    f"of values are positive, so negatives likely represent "
                    f"reversals, corrections, or returns.{seg_phrase}"
                ),
                "evidence": evidence,
            })

        # Extreme outliers (beyond 99.9th percentile)
        q_high = float(s.quantile(_EXTREME_QUANTILE))
        extreme_count = int((s > q_high).sum())
        if extreme_count > 0 and q_high > float(s.median()) * 10:
            insights.append({
                "type": "ANOMALY",
                "dimension": None,
                "metric": metric,
                "severity": "MEDIUM",
                "summary": (
                    f"{extreme_count:,} rows have extreme {metric} values "
                    f"(above {q_high:,.2f}, the 99.9th percentile). "
                    f"This is {round(q_high / max(float(s.median()), 1e-9), 1)}x "
                    f"the median value."
                ),
                "evidence": {
                    "extreme_count": extreme_count,
                    "threshold": round(q_high, 2),
                    "median": round(float(s.median()), 2),
                    "multiplier": round(q_high / max(float(s.median()), 1e-9), 2),
                },
            })

        # High zero ratio
        zero_pct = n_zero / n_total if n_total > 0 else 0
        if zero_pct > _ZERO_RATIO_THRESHOLD:
            insights.append({
                "type": "ANOMALY",
                "dimension": None,
                "metric": metric,
                "severity": "MEDIUM",
                "summary": (
                    f"{round(zero_pct * 100, 1)}% of {metric} values are zero. "
                    f"This may indicate missing data, inactive records, or "
                    f"a metric that only applies to a subset of rows."
                ),
                "evidence": {
                    "zero_count": n_zero,
                    "zero_pct": round(zero_pct, 4),
                    "total_rows": n_total,
                },
            })

    except Exception as e:
        log.debug(f"[DESCRIPTIVE] anomaly failed metric={metric}: {e}")

    return insights


# ─────────────────────────────────────────────────────────────────────────────
# COMPUTATION 4: VARIANCE DECOMPOSITION
# ─────────────────────────────────────────────────────────────────────────────

def _variance_insights(
    df: pd.DataFrame,
    dim: str,
    metric: str,
) -> list[dict[str, Any]]:
    """How much of metric's variance is explained by this dimension."""
    insights: list[dict] = []

    try:
        s = df[[dim, metric]].dropna()
        if len(s) < _MIN_SEGMENT_ROWS * 2:
            return []

        total_var = float(s[metric].var())
        if total_var < 1e-12:
            return []

        group_means = s.groupby(dim)[metric].mean()
        group_sizes = s.groupby(dim).size()
        grand_mean = float(s[metric].mean())

        # Between-group sum of squares / total sum of squares
        ss_between = float(((group_means - grand_mean) ** 2 * group_sizes).sum())
        ss_total = total_var * (len(s) - 1)

        if ss_total < 1e-12:
            return []

        explained = ss_between / ss_total

        if explained >= _VARIANCE_EXPLAINED_MIN:
            insights.append({
                "type": "VARIANCE_DRIVER",
                "dimension": dim,
                "metric": metric,
                "severity": "HIGH" if explained >= 0.30 else "MEDIUM",
                "summary": (
                    f"{dim} explains {round(explained * 100, 1)}% of the variance "
                    f"in {metric}. This dimension is a significant driver of "
                    f"differences in {metric} across the dataset."
                ),
                "evidence": {
                    "explained_variance_ratio": round(explained, 4),
                    "n_groups": len(group_means),
                    "total_variance": round(total_var, 4),
                },
            })

    except Exception as e:
        log.debug(f"[DESCRIPTIVE] variance failed dim={dim} metric={metric}: {e}")

    return insights


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def compute_descriptive_insights(
    df: pd.DataFrame,
    valid_metrics: list[str],
    dimensions: list[str],
) -> list[dict[str, Any]]:
    """
    Compute unconditional descriptive insights from a tabular dataset.

    Args:
        df:             post-sanitisation, post-semantic-mapping DataFrame
        valid_metrics:  numeric metric column names (from DatasetProfiler)
        dimensions:     categorical dimension column names (from DatasetProfiler)

    Returns:
        List of insight dicts, each with:
          type, dimension, metric, severity, summary, evidence

        Guaranteed non-empty when df has ≥1 metric and ≥1 dimension with ≥2 values.
        Returns [] only if inputs are structurally insufficient.
    """
    if df.empty or (not valid_metrics and not dimensions):
        return []

    selected_dims = _select_dimensions(df, dimensions)
    selected_metrics = _select_metrics(df, valid_metrics)

    if not selected_metrics:
        return []

    insights: list[dict[str, Any]] = []

    # ── Per-metric anomaly detection (no dimension needed) ──────────────
    for metric in selected_metrics:
        try:
            insights.extend(_anomaly_insights(df, metric, dimensions=selected_dims))
        except Exception as e:
            log.warning(f"[DESCRIPTIVE] anomaly scan failed for {metric}: {e}")

    # ── Per (dimension × metric) analysis ───────────────────────────────
    for dim in selected_dims:
        for metric in selected_metrics:
            try:
                insights.extend(_concentration_insights(df, dim, metric))
            except Exception:
                continue
            try:
                insights.extend(_ranked_insights(df, dim, metric))
            except Exception:
                continue
            try:
                insights.extend(_variance_insights(df, dim, metric))
            except Exception:
                continue

    # ── Sort: HIGH first, then MEDIUM, then LOW/INFO; metric name tiebreaker ──
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    insights.sort(key=lambda i: (
        severity_order.get(i.get("severity", "INFO"), 9),
        i.get("metric", ""),
        i.get("type", ""),
    ))

    # ── Bound output ────────────────────────────────────────────────────
    return insights[:_MAX_INSIGHTS]
