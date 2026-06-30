"""
aegis_ai/core/event_engine.py
================================
Event Engine — converts raw brain insights into the strict event schema
consumed by the decision synthesizer and validator.

Output schema (every event, no exceptions):
{
  "metric":       str,
  "role":         str,   # INPUT | OUTPUT | VALUE | COST | QUALITY | TRANSFER | UNKNOWN
  "direction":    str,   # UPWARD | DOWNWARD | STRUCTURAL
  "confidence":   float, # 0.0–1.0
  "magnitude_pct":float, # cusum_peak / threshold ratio (auditable)
  "zero_ratio":   float, # from reality_snapshot
  "ordered_data": bool,  # True if source data was time-ordered
  "evidence":     dict   # raw evidence block from detector
}

Contract:
  - Every field has a safe default — no KeyError possible downstream
  - Roles align exactly with decision_synthesizer.py role groups
  - ordered_data=False applies a 0.6x confidence penalty to BIAS signals
  - Identifier columns and sparse columns are rejected here (second gate
    after column_filter — belt-and-suspenders)
  - Deterministic: sorted column order, no randomness
"""

from __future__ import annotations

import re
import logging
from itertools import groupby as _groupby
from typing import Any

log = logging.getLogger("aegis_ai.core.event_engine")

# ─────────────────────────────────────────────────────────────────────────────
# ROLE REGISTRY
# Single source of truth — must match decision_synthesizer.py exactly
# ─────────────────────────────────────────────────────────────────────────────

_CANONICAL_ROLES: dict[str, str] = {
    # Inputs / spend
    "Budget": "INPUT", "Ad_Spend": "INPUT", "Cost": "INPUT",
    "COGS": "INPUT", "Operating_Expense": "INPUT",
    "Maintenance_Cost": "INPUT", "Delivery_Cost": "INPUT",
    # Outputs / volume
    "Revenue": "OUTPUT", "Revenue_2": "OUTPUT",       # collision-suffixed
    "Quantity": "OUTPUT", "Production_Volume": "OUTPUT",
    "Headcount": "OUTPUT", "Fill_Rate": "OUTPUT",
    "Clicks": "INPUT",        # clicks = input to conversion funnel
    "Impressions": "INPUT",
    "Sessions": "INPUT",
    "Conversions": "OUTPUT",
    # Value / efficiency
    "ROI": "VALUE", "Profit_Margin": "VALUE", "Profit": "VALUE",
    "CLV": "VALUE", "NPS": "VALUE", "Performance_Score": "VALUE",
    "OEE": "VALUE", "On_Time_Rate": "VALUE", "Conversion_Rate": "VALUE",
    "ROAS": "VALUE", "CTR": "VALUE",
    # Cost / pricing
    "Price_per_Unit": "COST", "Bundle_Price": "COST",
    "Discount": "COST", "Discount_Rate": "COST", "Tax": "COST",
    # Quality / risk
    "Defect_Rate": "QUALITY", "Attrition": "QUALITY",
    "Churn_Rate": "QUALITY", "Absenteeism": "QUALITY",
    "Downtime": "QUALITY", "Returns": "QUALITY",
    "Defect_Count": "QUALITY",
    # Transfers / inventory
    "Inventory_Level": "TRANSFER",
    "RETAIL TRANSFERS": "TRANSFER",
    "Warehouse_Sales": "OUTPUT",
    "Retail_Sales": "OUTPUT",
}

# Keyword fallback (applied to raw metric name when not in canonical registry)
_ROLE_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(transfer|inventory|stock|warehouse|movement|logistics|freight|shipping)\b", re.I), "TRANSFER"),
    (re.compile(r"\b(budget|spend|cost|expense|opex|capex|investment|cogs|overhead)\b", re.I), "INPUT"),
    (re.compile(r"\b(revenue|sales|income|turnover|output|volume|units|quantity|qty|orders|conversions|bookings|signups)\b", re.I), "OUTPUT"),
    (re.compile(r"\b(roi|roas|margin|profit|score|efficiency|performance|nps|clv|satisfaction|rating|ctr|cvr)\b", re.I), "VALUE"),
    (re.compile(r"\b(price|pricing|tariff|fee|discount|rebate|markup|bundle)\b", re.I), "COST"),
    (re.compile(r"\b(defect|churn|attrition|return|refund|downtime|absence|error|fault|reject|complaint|incident)\b", re.I), "QUALITY"),
]

# Columns that must never become events regardless of what brain_output says
_ID_PATTERN = re.compile(
    r"\b(id|code|key|number|no|num|pk|fk|ref|uuid|guid|sku|serial|index|idx)\b"
    r"|(?:No|ID|Id|Code|Key|Num|Ref|Idx)$",
    re.IGNORECASE,
)

_TEMPORAL_PATTERN = re.compile(
    r"\b(year|month|week|day|quarter|fy|fiscal)\b",
    re.IGNORECASE,
)

# Minimum magnitude ratio (cusum_peak / threshold) to treat a signal as real
_MIN_MAGNITUDE = 0.02

# Zero-ratio threshold above which CUSUM is unreliable for a metric
_SPARSE_ZERO_THRESHOLD = 0.50

# Confidence penalty multiplier for unordered BIAS signals
_UNORDERED_PENALTY = 0.6

# Fallback: if primary filtering yields 0 events, select top N with capped confidence
_FALLBACK_MAX = 3
_FALLBACK_CONFIDENCE_CAP = 0.5

# F-04: Behavioral role overrides — populated by normalize_events() from resolve_metric_roles()
_behavioral_roles: dict[str, str] = {}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def normalize_events(
    brain_insights: list[dict[str, Any]],
    reality_snapshot: dict[str, Any],
    *,
    ordered_data: bool = False,
    metric_roles: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Convert raw brain insight dicts into the strict event schema.

    Args:
        brain_insights:   insights list from run_company_brain_v2()
        reality_snapshot: {"numeric": {metric: {mean, std, zero_ratio, ...}}}
        ordered_data:     True if source df had a real time column
        metric_roles:     F-04: behavioral role overrides from resolve_metric_roles()

    Returns:
        List of validated, normalized events in strict schema.
        Empty list if no valid events found — caller should handle gracefully.
    """
    numeric_stats: dict[str, Any] = reality_snapshot.get("numeric", {})
    _behavioral_roles.update(metric_roles or {})   # F-04: populate module-level cache
    raw_events: list[dict] = []

    for insight in brain_insights:
        try:
            event = _convert_insight(insight, numeric_stats, ordered_data)
            if event is not None:
                raw_events.append(event)
        except Exception as e:
            log.warning(f"[EVENT_ENGINE] Failed to convert insight: {e}")
            continue

    # ── Fallback: if strict filtering killed everything, re-run relaxed ──
    if not raw_events and brain_insights:
        for insight in brain_insights:
            try:
                event = _convert_insight(
                    insight, numeric_stats, ordered_data, relaxed=True,
                )
                if event is not None:
                    event["confidence"] = min(
                        event["confidence"], _FALLBACK_CONFIDENCE_CAP,
                    )
                    raw_events.append(event)
            except Exception:
                continue
        # Keep top N by magnitude*confidence, metric name as tiebreaker
        raw_events.sort(
            key=lambda e: (-e["magnitude_pct"] * e["confidence"], e["metric"]),
        )
        raw_events = raw_events[:_FALLBACK_MAX]

    # ── Per-primitive cap: prevent one detector from flooding the pipeline ──
    # Keep strongest signals per primitive to ensure decision diversity.
    _PRIMITIVE_CAP = {"DOMINANCE": 3, "BIAS": 3, "TRADEOFF": 2, "REGIME_SHIFT": 2}
    if raw_events:
        capped: list[dict] = []
        # Group by primitive, sort each by magnitude*confidence desc
        raw_events.sort(key=lambda e: e.get("primitive", ""))
        for prim, group in _groupby(raw_events, key=lambda e: e.get("primitive", "")):
            members = sorted(
                group,
                key=lambda e: (-e["magnitude_pct"] * e["confidence"], e["metric"]),
            )
            cap = _PRIMITIVE_CAP.get(prim, 3)
            capped.extend(members[:cap])
        raw_events = capped

    # Sort for determinism (metric name → direction)
    raw_events.sort(key=lambda e: (e["metric"], e["direction"]))
    return raw_events


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL CONVERSION
# ─────────────────────────────────────────────────────────────────────────────

def _convert_insight(
    insight: dict[str, Any],
    numeric_stats: dict[str, Any],
    ordered_data: bool,
    *,
    relaxed: bool = False,
) -> dict[str, Any] | None:

    primitive = insight.get("primitive", "")

    # ── Extract metric ─────────────────────────────
    if primitive == "TRADEOFF":
        metrics = insight.get("metrics") or []
        metric = metrics[0] if metrics else None
    else:
        metric = insight.get("metric")

    if not metric:
        return None

    # ── Gate 1: identifier / temporal ─────────────
    if _ID_PATTERN.search(metric):
        return None

    if _TEMPORAL_PATTERN.search(metric):
        return None

    # ── Gate 3: magnitude ─────────────────────────
    evidence = insight.get("evidence") or {}
    col_stats_early = numeric_stats.get(metric, {})

    if primitive in ("DOMINANCE", "TRADEOFF", "REGIME_SHIFT"):
        magnitude_pct = float(insight.get("signal_score", 0.0))
    else:
        # W2 fix: use correctness layer's 30/70 split means as the single
        # source of truth. Previously we mixed `evidence.baseline_mean`
        # (detector view) with `col_stats.mean` (reality reader view),
        # which produced wild magnitudes (~448%) from scale/slice mismatches
        # on stable datasets. The correctness block carries matched-slice
        # baseline/current means; prefer it unconditionally.
        correctness_block = insight.get("correctness") or {}
        if correctness_block:
            baseline_mean_ev = float(correctness_block.get("baseline_mean", 0.0))
            current_mean_ev  = float(correctness_block.get("current_mean", baseline_mean_ev))
        else:
            # Fallback: use the detector's own split means if it carried
            # them (hardened BiasDetector does). Only fall back to the
            # old mixed-scale path as a last resort.
            baseline_mean_ev = float(
                evidence.get("split_baseline_mean",
                             evidence.get("baseline_mean", 0.0))
            )
            current_mean_ev = float(
                evidence.get("split_current_mean",
                             col_stats_early.get("mean", baseline_mean_ev))
            )

        if abs(baseline_mean_ev) > 1e-9:
            magnitude_pct = abs(current_mean_ev - baseline_mean_ev) / abs(baseline_mean_ev) * 100.0
        else:
            magnitude_pct = 0.0
        # Cap at 200% (W2): anything higher is almost certainly a scaling
        # artefact, not a real business movement. Log when clamping so the
        # downstream audit trail surfaces likely data-quality issues.
        if magnitude_pct > 200.0:
            log.warning(
                f"[MAGNITUDE_CLAMP] {metric}: raw={magnitude_pct:.1f}% "
                f"clamped to 200.0% — likely scale/slice mismatch"
            )
            magnitude_pct = 200.0

    # In relaxed (fallback) mode, halve the magnitude threshold to allow
    # marginal signals through — they'll be capped at _FALLBACK_CONFIDENCE_CAP.
    min_mag = (_MIN_MAGNITUDE / 2.0) if relaxed else _MIN_MAGNITUDE
    if magnitude_pct < min_mag and primitive != "REGIME_SHIFT":
        return None

    # ── Gate 4: sparse ────────────────────────────
    col_stats = numeric_stats.get(metric, {})
    zero_ratio = float(col_stats.get("zero_ratio", 0.0))

    if zero_ratio > _SPARSE_ZERO_THRESHOLD and not relaxed:
        return None

    # ── Gate 4.5: EFFECT SIZE ─────────────────────
    # Use reality_snapshot (col_stats) as sole truth for current state.
    # For baseline, prefer correctness layer's computed baseline (30/70 split)
    # over evidence.baseline_mean which can be on a different scale.
    correctness_block = insight.get("correctness", {})
    if correctness_block:
        baseline_mean = float(correctness_block.get("baseline_mean", 0.0))
        current_mean  = float(correctness_block.get("current_mean", baseline_mean))
    else:
        baseline_mean = float(col_stats.get("mean", 0.0))
        current_mean  = baseline_mean

    delta_pct = abs(current_mean - baseline_mean) / (abs(baseline_mean) + 1e-9)

    # BIAS and DOMINANCE have internal quality gates (CUSUM threshold,
    # dominance coverage). Effect-size is redundant for them and broken
    # on first upload where baseline_stats == reality_snapshot.
    if primitive not in ("BIAS", "DOMINANCE", "TRADEOFF", "REGIME_SHIFT") and not relaxed:
        if delta_pct < 0.005:
            return None

    # ── REGIME SHIFT — F-06: restricted to BIAS only ─────────
    # Only BIAS signals (temporal drift) can be promoted to REGIME_SHIFT.
    # DOMINANCE and TRADEOFF are structural/correlational — large effect
    # sizes do not make them regime shifts.
    # delta_pct must be computed from SAME-SCALE baselines (correctness layer)
    # to prevent false promotions from stale evidence blocks.
    if delta_pct > 0.5 and primitive == "BIAS":
        direction = "UPWARD" if current_mean > baseline_mean else "DOWNWARD"
        primitive = "REGIME_SHIFT"
    else:
        direction = (
            insight.get("subtype")
            or insight.get("direction")
            or "UNKNOWN"
        ).upper()

        # TRADEOFF direction is POSITIVE/NEGATIVE (correlation sign),
        # not a temporal direction. Map to STRUCTURAL — tradeoffs
        # describe a structural relationship between two metrics.
        if primitive == "TRADEOFF" and direction in ("POSITIVE", "NEGATIVE"):
            direction = "STRUCTURAL"

        if direction not in ("UPWARD", "DOWNWARD", "STRUCTURAL"):
            direction = _infer_direction_from_primitive(insight)
            if direction is None:
                return None

    # ── Gate 5: CV check ─────────────────────────
    mean = abs(float(col_stats.get("mean", 1.0)))
    std  = abs(float(col_stats.get("std", 0.0)))
    cv   = (std / mean) if mean > 0 else 0.0

    if cv > 3.0 and _ID_PATTERN.search(metric):
        return None

    # ── Confidence ───────────────────────────────
    # F-08: No post-hoc mutations here. Effect-size and ordered-data
    # factors are now consolidated into compute_confidence() in the
    # orchestrator. The confidence arriving from the brain is final.
    confidence = float(insight.get("confidence", 0.0))

    # ── Role ─────────────────────────────────────
    role = _assign_role(metric)

    return {
        "metric":        metric,
        "role":          role,
        "direction":     direction,
        "confidence":    round(confidence, 4),
        "magnitude_pct": round(magnitude_pct, 4),
        "zero_ratio":    round(zero_ratio, 4),
        "ordered_data":  ordered_data,
        "primitive":     primitive,
        "evidence":      evidence,
        "segment_context": insight.get("segment_context") or [],
        "metrics":       insight.get("metrics"),
        "signal_score":  insight.get("signal_score"),
        "pair_classification": insight.get("pair_classification"),
    }


def _infer_direction_from_primitive(insight: dict) -> str | None:
    """
    For DOMINANCE insights (no UPWARD/DOWNWARD subtype), infer a
    direction from the primitive subtype for downstream consumption.
    Returns None if no meaningful direction can be inferred.

    FIX F-01: Dominance is a structural property (concentration), not a
    temporal direction (decline). Return STRUCTURAL instead of DOWNWARD
    to prevent false decline signals for concentrated-but-stable metrics.
    """
    subtype = (insight.get("subtype") or "").upper()
    if subtype in ("CATEGORICAL", "POINT", "RANGE_STD", "RANGE_QUANTILE"):
        return "STRUCTURAL"  # F-01: non-directional — concentration, not decline
    return None


def _assign_role(metric: str) -> str:
    """
    Assign economic role. Priority:
      1. Canonical registry (exact name match)
      2. Keyword regex fallback
      3. F-04: Behavioral inference from metric_role_inference.py
    Returns UNKNOWN only when nothing matches — never raises.
    """
    if metric in _CANONICAL_ROLES:
        return _CANONICAL_ROLES[metric]

    # Also check Revenue_2, Revenue_3 suffixes
    base = re.sub(r"_\d+$", "", metric)
    if base in _CANONICAL_ROLES:
        return _CANONICAL_ROLES[base]

    for pattern, role in _ROLE_KEYWORDS:
        if pattern.search(metric):
            return role

    # F-04: Behavioral fallback — uses distributional signatures
    if metric in _behavioral_roles:
        return _behavioral_roles[metric]

    return "UNKNOWN"