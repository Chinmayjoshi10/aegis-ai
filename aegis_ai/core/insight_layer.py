"""
aegis_ai/core/insight_layer.py
=================================
Universal Pattern Engine — four domain-agnostic detectors producing
exactly 3 balanced, prioritized insights.

Pipeline:
  data → signals → correctness → segments → insight_layer → narration

Design:
  1. Each detector operates on ABSTRACT PATTERN TYPES, not metric names.
     Metric names are resolved only in the output stage.
  2. Selection is SLOT-BASED for balance:
       Slot 1 → highest-scored RISK (if any)
       Slot 2 → highest-scored STRUCTURAL: TRADEOFF or LEAKAGE (if any)
       Slot 3 → highest-scored OPPORTUNITY (if any)
     Unfilled slots are backfilled from the remaining ranked pool.
  3. Scoring: importance = sigmoid(magnitude) × sqrt(coverage) × confidence
  4. Returns exactly TOP 3 insights (or fewer if candidates are scarce).

Output types:
  RISK        — concentration or decline creating structural fragility
  TRADEOFF    — two metrics moving in opposing directions
  LEAKAGE     — negative values in a positive-dominant metric
  OPPORTUNITY — segment outperforming global baseline significantly

Safety:
  - No causation claims
  - No business domain assumptions
  - No financial projections
  - Only observable structural relationships
"""

from __future__ import annotations

import logging
import math
from typing import Any

log = logging.getLogger("aegis_ai.core.insight_layer")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

_TARGET_INSIGHTS           = 3      # always return exactly this many (if candidates permit)
_CONCENTRATION_RISK_SHARE  = 0.70   # top segment >= 70% share → RISK candidate
_CONCENTRATION_HIGH_SHARE  = 0.80   # >= 80% → amplified confidence
_OPPORTUNITY_MIN_DEVIATION     = 0.10   # segment mean >= +10% above global
_MIN_SEGMENT_COVERAGE          = 0.01   # primary filter: segment >= 1% of total rows
_MIN_SEGMENT_COVERAGE_FALLBACK = 0.005  # fallback: 0.5% — used when primary finds nothing
_LEAKAGE_MIN_NEGATIVE_ROWS     = 1      # any negatives qualify

# Structural insight types (fills slot 2)
_STRUCTURAL_TYPES = {"TRADEOFF", "LEAKAGE"}


# ─────────────────────────────────────────────────────────────────────────────
# SCORING
# importance = sigmoid(magnitude) × sqrt(coverage) × confidence
# ─────────────────────────────────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-float(x)))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _score(magnitude: float, coverage: float, confidence: float) -> float:
    return round(
        _sigmoid(abs(magnitude))
        * math.sqrt(min(max(float(coverage), 0.0), 1.0))
        * min(max(float(confidence), 0.0), 1.0),
        6,
    )


# ─────────────────────────────────────────────────────────────────────────────
# ABSTRACT PATTERN STRUCTS
# Internal representation before metric names are bound to output text.
# ─────────────────────────────────────────────────────────────────────────────

def _make_candidate(
    *,
    insight_type: str,
    title: str,
    fact: str,
    pattern: str,
    impact: str,
    confidence: float,
    importance: float,
    key: tuple,
) -> dict[str, Any]:
    return {
        "type":         insight_type,
        "title":        title,
        "fact":         fact,
        "pattern":      pattern,
        "impact":       impact,
        "confidence":   round(confidence, 4),
        "_importance":  importance,
        "_key":         key,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR 1: TRADEOFF
# Abstract: two validated directional signals — one UPWARD, one DOWNWARD.
# Resolution: metric names bound at output time.
# ─────────────────────────────────────────────────────────────────────────────

def _detect_tradeoffs(
    validated_signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    For every (UPWARD metric, DOWNWARD metric) pair, emit a TRADEOFF.
    Abstraction: signals are treated as (direction, magnitude, confidence) tuples.
    Metric names appear only in final title/fact strings.
    """
    upward   = [s for s in validated_signals if s.get("direction") == "UPWARD"]
    downward = [s for s in validated_signals if s.get("direction") == "DOWNWARD"]

    candidates: list[dict[str, Any]] = []

    for u in upward:
        for d in downward:
            m_up    = u.get("metric", "Metric A")
            m_down  = d.get("metric", "Metric B")
            conf    = round((float(u.get("confidence", 0)) + float(d.get("confidence", 0))) / 2, 4)
            mag     = (float(u.get("magnitude_pct", 0)) + float(d.get("magnitude_pct", 0))) / 2

            candidates.append(_make_candidate(
                insight_type="TRADEOFF",
                title=(
                    f"{m_up} trending upward while {m_down} declines — "
                    f"structural tension detected"
                ),
                fact=(
                    f"{m_up} is on a validated UPWARD trajectory. "
                    f"{m_down} is on a validated DOWNWARD trajectory. "
                    f"Both passed directional correctness validation."
                ),
                pattern=(
                    f"These two metrics are moving in structurally opposing directions "
                    f"across the full dataset. This is a global pattern — not isolated "
                    f"to any single segment — confirmed by independent signal analysis."
                ),
                impact=(
                    f"Opposing movements between {m_up} (+trend, {round(u.get('confidence',0)*100,1)}% confidence) "
                    f"and {m_down} (-trend, {round(d.get('confidence',0)*100,1)}% confidence) "
                    f"create structural tension: gains in one metric coincide with losses in "
                    f"the other. This constrains total upside — improvement in both "
                    f"directions simultaneously is not consistent with the observed data."
                ),
                confidence=conf,
                importance=_score(magnitude=mag, coverage=1.0, confidence=conf),
                key=("TRADEOFF", frozenset([m_up, m_down])),
            ))

    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR 2: RISK
# Abstract: a metric's total is dominated by a single dimensional segment.
# Resolution: metric and dimension names bound at output time.
# ─────────────────────────────────────────────────────────────────────────────

def _detect_risks(
    validated_signals: list[dict[str, Any]],
    descriptive_insights: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    For each CONCENTRATION insight where the top segment holds >= 70% of
    a metric's total, emit a RISK. Amplified if the metric is also DOWNWARD.

    Abstraction: concentration is expressed as (top_share, coverage, n_segments).
    Metric names appear only in output strings.
    """
    declining = {
        s.get("metric") for s in validated_signals
        if s.get("direction") == "DOWNWARD"
    }

    candidates: list[dict[str, Any]] = []

    for di in descriptive_insights:
        if di.get("type") != "CONCENTRATION":
            continue

        ev          = di.get("evidence", {})
        top_share   = float(ev.get("top_share", 0))
        if top_share < _CONCENTRATION_RISK_SHARE:
            continue

        metric      = di.get("metric", "the metric")
        dimension   = di.get("dimension", "the dimension")
        top_seg     = ev.get("top_segment", "one segment")
        top3_share  = float(ev.get("top3_share", top_share))
        hhi         = float(ev.get("hhi", 0))
        n_segs      = int(ev.get("total_segments", 1))
        is_down     = metric in declining

        base_conf   = 0.85 if top_share >= _CONCENTRATION_HIGH_SHARE else 0.65
        conf        = round(min(base_conf + (0.10 if is_down else 0.0), 0.99), 4)

        candidates.append(_make_candidate(
            insight_type="RISK",
            title=(
                f"{'Declining ' if is_down else ''}{metric} is structurally "
                f"concentrated — {round(top_share * 100, 1)}% in one {dimension} segment"
            ),
            fact=(
                f"'{top_seg}' accounts for {round(top_share * 100, 1)}% of total {metric} "
                f"across {n_segs} {dimension} segments. "
                f"Top 3 segments collectively: {round(top3_share * 100, 1)}%. "
                f"HHI concentration index: {round(hhi, 3)}."
            ),
            pattern=(
                f"Structural concentration: {round(top_share * 100, 1)}% of {metric} "
                f"is held by a single segment out of {n_segs}. "
                + (
                    f"{metric} is simultaneously on a validated DOWNWARD trend — "
                    f"concentration amplifies exposure to this decline. "
                    if is_down else
                    f"This creates a single point of dependency for {metric}. "
                )
                + f"HHI of {round(hhi, 3)} confirms the distribution is far from uniform."
            ),
            impact=(
                f"A {round((1 - top_share) * 100, 1)}% reduction in the contribution "
                f"of '{top_seg}' would eliminate most of the dataset's {metric}. "
                f"With {n_segs} segments and {round(top_share * 100, 1)}% in one, "
                f"diversification is critically low — any structural shift in "
                f"'{top_seg}' propagates with full magnitude to {metric} totals."
            ),
            confidence=conf,
            importance=_score(magnitude=top_share, coverage=top3_share, confidence=conf),
            key=("RISK", frozenset([metric, dimension])),
        ))

    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR 3: LEAKAGE
# Abstract: negative values exist in a metric where the vast majority are positive.
# This is structurally inconsistent — the negatives represent reversals or loss.
# ─────────────────────────────────────────────────────────────────────────────

def _detect_leakage(
    descriptive_insights: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    For each ANOMALY with negative_count > 0 in a positive-dominant metric,
    emit a LEAKAGE.

    Abstraction: (neg_ratio, neg_total, positive_pct) — no metric assumptions.
    Metric name appears only in output strings.
    Now includes segment attribution when available from descriptive profiler.
    """
    candidates: list[dict[str, Any]] = []

    for di in descriptive_insights:
        if di.get("type") != "ANOMALY":
            continue

        ev          = di.get("evidence", {})
        neg_count   = int(ev.get("negative_count", 0))
        if neg_count < _LEAKAGE_MIN_NEGATIVE_ROWS:
            continue

        metric       = di.get("metric", "the metric")
        total_rows   = max(int(ev.get("total_rows", 1)), 1)
        neg_total    = float(ev.get("negative_total", 0))
        positive_pct = float(ev.get("positive_pct", 1.0))
        neg_ratio    = neg_count / total_rows
        conf         = 0.90 if neg_ratio > 0.01 else 0.70

        # Segment attribution (from descriptive_profiler)
        leak_seg = ev.get("top_segment")
        seg_phrase = ""
        if leak_seg:
            seg_phrase = f" concentrated in {leak_seg['value']}"

        candidates.append(_make_candidate(
            insight_type="LEAKAGE",
            title=(
                f"{metric} contains {round(neg_ratio * 100, 2)}% negative values — "
                f"structural reversals detected"
                + (f" (driven by {leak_seg['value']})" if leak_seg else "")
            ),
            fact=(
                f"{neg_count:,} of {total_rows:,} rows ({round(neg_ratio * 100, 2)}%) "
                f"have negative {metric} values. "
                f"Cumulative negative magnitude: {neg_total:,.2f}.{seg_phrase}"
            ),
            pattern=(
                f"{round(positive_pct * 100, 1)}% of {metric} values are positive, "
                f"establishing it as a predominantly positive metric. "
                f"The {round(neg_ratio * 100, 2)}% of negative rows are structurally "
                f"anomalous — they represent reversals, corrections, or returns "
                f"counter to the metric's primary direction."
            ),
            impact=(
                f"The {round(neg_ratio * 100, 2)}% negative rows reduce "
                f"{metric}'s effective aggregate. "
                f"A net loss of {abs(neg_total):,.2f} is embedded within {metric}. "
                f"This is a recurring structural pattern — not a single outlier — "
                f"and its effect compounds at scale across {total_rows:,} rows."
                + (f" Primary source: {leak_seg['value']} ({leak_seg['dimension']})." if leak_seg else "")
            ),
            confidence=conf,
            importance=_score(magnitude=neg_ratio * 10, coverage=neg_ratio, confidence=conf),
            key=("LEAKAGE", frozenset([metric])),
        ))

    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# OPPORTUNITY CANDIDATE BUILDER
# Shared by both primary and fallback passes — builds the OPPORTUNITY dict.
# ─────────────────────────────────────────────────────────────────────────────

def _update_best(
    best: dict,
    ctx: dict[str, Any],
    metric: str,
    deviation: float,
    coverage: float,
    conf: float,
    score: float,
) -> None:
    """Build and store the best OPPORTUNITY candidate for a metric."""
    seg_val = ctx.get("segment_value", "a segment")
    dim     = ctx.get("dimension", "a dimension")
    s_mean  = float(ctx.get("segment_mean", 0))
    g_mean  = float(ctx.get("global_mean", 0))
    pct_str = f"{round(deviation * 100, 1)}%"
    cov_str = f"{round(coverage * 100, 2)}%"

    best[metric] = _make_candidate(
        insight_type="OPPORTUNITY",
        title=(
            f"{metric} in '{seg_val}' ({dim}) outperforms "
            f"global baseline by {pct_str}"
        ),
        fact=(
            f"{metric} in '{seg_val}' ({dim}) averages {s_mean:.4g}, "
            f"versus a global average of {g_mean:.4g} "
            f"(+{pct_str} above global baseline, "
            f"covering {cov_str} of total rows)."
        ),
        pattern=(
            f"{metric} is on a validated UPWARD global trend. "
            f"Within '{seg_val}', this trend is amplified by {pct_str} "
            f"above the global mean — a statistically meaningful "
            f"positive deviation visible in {cov_str} of the dataset."
        ),
        impact=(
            f"'{seg_val}' concentrates {metric} performance "
            f"{pct_str} above baseline. "
            f"This segment accounts for {cov_str} of rows — "
            f"the upward global trend is not uniformly distributed. "
            f"Segments with {pct_str}+ deviation indicate structural "
            f"conditions that drive the broader {metric} trend."
        ),
        confidence=conf,
        importance=score,
        key=("OPPORTUNITY", frozenset([metric, dim])),
    )


# ─────────────────────────────────────────────────────────────────────────────
# DETECTOR 4: OPPORTUNITY
# Abstract: a segment outperforms the global mean on a validated UPWARD metric.
# One opportunity per metric — highest deviation segment wins.
# ─────────────────────────────────────────────────────────────────────────────

def _detect_opportunities(
    validated_signals: list[dict[str, Any]],
    segment_decisions: dict[str, list[dict[str, Any]]],
    total_rows: int,
) -> list[dict[str, Any]]:
    """
    For each UPWARD metric, find the segment with the highest positive deviation
    above global mean (min +10%, min 3% of total rows). One per metric.

    Abstraction: (deviation, coverage) drives scoring. Metric/segment names
    appear only in output strings.
    """
    upward_metrics = {
        s.get("metric")
        for s in validated_signals
        if s.get("direction") == "UPWARD"
    }

    if not upward_metrics:
        return []

    # {metric → best candidate dict}
    best: dict[str, dict] = {}

    # Primary pass: coverage >= _MIN_SEGMENT_COVERAGE
    for _label, contexts in segment_decisions.items():
        if not isinstance(contexts, list):
            continue
        for ctx in contexts:
            if ctx.get("type") != "SEGMENT_CONTEXT":
                continue

            metric    = ctx.get("metric", "")
            if metric not in upward_metrics:
                continue

            deviation = float(ctx.get("deviation", 0))
            if deviation < _OPPORTUNITY_MIN_DEVIATION:
                continue

            seg_rows  = int(ctx.get("segment_rows", 0))
            coverage  = seg_rows / max(total_rows, 1)
            if coverage < _MIN_SEGMENT_COVERAGE:
                continue

            conf      = round(min(0.55 + deviation * 0.6, 0.92), 4)
            score     = _score(magnitude=deviation, coverage=coverage, confidence=conf)

            if metric not in best or score > best[metric]["_importance"]:
                _update_best(best, ctx, metric, deviation, coverage, conf, score)

    # Fallback pass: if no candidate found for an upward metric,
    # accept any segment with deviation >= threshold and coverage >= 0.5%
    # This guarantees OPPORTUNITY surfaces when the dataset has small segments.
    for metric in upward_metrics:
        if metric in best:
            continue  # already found by primary pass
        top_dev, top_ctx = 0.0, None
        for _label, contexts in segment_decisions.items():
            if not isinstance(contexts, list):
                continue
            for ctx in contexts:
                if ctx.get("type") != "SEGMENT_CONTEXT":
                    continue
                if ctx.get("metric", "") != metric:
                    continue
                deviation = float(ctx.get("deviation", 0))
                if deviation < _OPPORTUNITY_MIN_DEVIATION:
                    continue
                seg_rows = int(ctx.get("segment_rows", 0))
                coverage = seg_rows / max(total_rows, 1)
                if coverage < _MIN_SEGMENT_COVERAGE_FALLBACK:
                    continue
                if deviation > top_dev:
                    top_dev, top_ctx = deviation, ctx
        if top_ctx is not None:
            coverage = int(top_ctx.get("segment_rows", 0)) / max(total_rows, 1)
            conf = round(min(0.50 + top_dev * 0.5, 0.88), 4)  # slightly lower conf for fallback
            score = _score(magnitude=top_dev, coverage=coverage, confidence=conf)
            _update_best(best, top_ctx, metric, top_dev, coverage, conf, score)

    return list(best.values())


# ─────────────────────────────────────────────────────────────────────────────
# SLOT-BASED BALANCED SELECTION
# Guarantees at least one RISK, one STRUCTURAL, one OPPORTUNITY if available.
# Falls back to pure rank-ordering to fill remaining slots.
# ─────────────────────────────────────────────────────────────────────────────

def _select_balanced(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Slot-based selection for balanced output:
      Slot 1 — best RISK
      Slot 2 — best STRUCTURAL (TRADEOFF or LEAKAGE)
      Slot 3 — best OPPORTUNITY
    Unfilled slots are backfilled from remaining ranked candidates.
    Deduplication by (type, metric-set) key throughout.
    """
    # Sort all candidates by importance desc, then type for determinism
    _TYPE_PRIORITY = {"RISK": 0, "LEAKAGE": 1, "TRADEOFF": 2, "OPPORTUNITY": 3}
    ranked = sorted(
        candidates,
        key=lambda c: (-c.get("_importance", 0), _TYPE_PRIORITY.get(c.get("type", ""), 9), c.get("title", "")),
    )

    seen_keys: set = set()
    selected: list[dict] = []

    def _pick(pool: list[dict], type_filter=None) -> dict | None:
        for c in pool:
            key = c.get("_key", ("?", id(c)))
            hk  = (key[0], key[1]) if isinstance(key, tuple) and isinstance(key[1], frozenset) else key
            if hk in seen_keys:
                continue
            if type_filter is not None and c.get("type") not in type_filter:
                continue
            seen_keys.add(hk)
            return c
        return None

    # Slot 1: best RISK
    risk = _pick(ranked, {"RISK"})
    if risk:
        selected.append(risk)

    # Slot 2: best STRUCTURAL
    structural = _pick(ranked, _STRUCTURAL_TYPES)
    if structural:
        selected.append(structural)

    # Slot 3: best OPPORTUNITY
    opp = _pick(ranked, {"OPPORTUNITY"})
    if opp:
        selected.append(opp)

    # Backfill from remaining ranked pool (no type filter) up to _TARGET_INSIGHTS
    while len(selected) < _TARGET_INSIGHTS:
        filler = _pick(ranked)
        if filler is None:
            break
        selected.append(filler)

    # Strip internal keys before returning
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in selected]


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def generate_insights(
    validated_signals: list[dict[str, Any]],
    segment_decisions: dict[str, list[dict[str, Any]]],
    descriptive_insights: list[dict[str, Any]],
    total_rows: int = 0,
    data_understanding: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Run all four universal pattern detectors and return exactly 3 balanced,
    prioritized insights (or fewer if candidates are scarce).

    Selection order (slot-based):
      1. Best RISK (concentration)
      2. Best STRUCTURAL (TRADEOFF or LEAKAGE)
      3. Best OPPORTUNITY

    Unfilled slots are backfilled from remaining ranked pool.

    Args:
        validated_signals:    corrected events from correctness_layer
        segment_decisions:    output of segment_engine.generate_segment_decisions
        descriptive_insights: output of descriptive_profiler.compute_descriptive_insights
        total_rows:           total DataFrame row count (for coverage computation)
        data_understanding:   {"key_metrics": [...], "important_dimensions": [...]}

    Returns:
        List of 0–3 insight dicts, each with:
          type, title, fact, pattern, impact, confidence
    """
    key_metrics = (
        data_understanding.get("key_metrics", [])
        if data_understanding
        else []
    )
    if key_metrics:
        key_metric_set = set(key_metrics)
        validated_signals = [
            s for s in validated_signals
            if s.get("metric") in key_metric_set
        ]
        descriptive_insights = [
            di for di in descriptive_insights
            if di.get("metric") in key_metric_set
        ]
        segment_decisions = {
            label: [
                ctx for ctx in contexts
                if isinstance(ctx, dict) and ctx.get("metric") in key_metric_set
            ]
            if isinstance(contexts, list)
            else contexts
            for label, contexts in segment_decisions.items()
        }

    all_candidates: list[dict[str, Any]] = []

    for detector, args in [
        (_detect_tradeoffs,     (validated_signals,)),
        (_detect_risks,         (validated_signals, descriptive_insights)),
        (_detect_leakage,       (descriptive_insights,)),
        (_detect_opportunities, (validated_signals, segment_decisions, total_rows)),
    ]:
        try:
            all_candidates.extend(detector(*args))
        except Exception as exc:
            log.warning(f"[INSIGHT_LAYER] {detector.__name__} failed: {exc}")

    if not all_candidates:
        return []

    result = _select_balanced(all_candidates)

    log.info(
        f"[INSIGHT_LAYER] {len(all_candidates)} candidates "
        f"→ {len(result)} insights (target={_TARGET_INSIGHTS})"
    )
    return result
