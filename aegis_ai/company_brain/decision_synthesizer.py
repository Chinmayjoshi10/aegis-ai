"""
aegis_ai/company_brain/decision_synthesizer.py
================================================
Universal Decision Synthesizer — converts normalized events into
clear, actionable, business-level decisions.

Upgrades vs previous version:
  - Decisions now include: title, summary, priority (HIGH/MEDIUM/LOW)
  - Consistent deduplication via fingerprinting
  - No padding fallback (silence is correct)
  - Deterministic sort: impact*confidence desc, type asc tiebreaker
  - deduplicate_semantic_mappings() and detect_composite_timestamp()
    remain here (used by routes.py)
"""

from __future__ import annotations

import re
import hashlib
from typing import Any

from aegis_ai.company_brain.decision_enricher import enrich_decisions   # noqa: F401 (re-exported)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

_MIN_MAGNITUDE_PCT    = 0.02
_SPARSE_ZERO_RATIO    = 0.50
_CV_IDENTIFIER_LIMIT  = 3.0
_MAX_DECISIONS        = 3

_ID_PATTERN = re.compile(
    r"\b(id|code|key|number|no|num|pk|fk|ref|uuid|guid|sku|serial|index|idx)\b"
    r"|(?:No|ID|Id|Code|Key|Num|Ref|Idx)$",
    re.IGNORECASE,
)
_TEMPORAL_PATTERN = re.compile(
    r"\b(year|month|week|day|quarter|fy|fiscal)\b",
    re.IGNORECASE,
)

_UNORDERED_BIAS_PENALTY = 0.6


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL VALIDATION  (second gate — event_engine is first)
# ─────────────────────────────────────────────────────────────────────────────

def _is_trustworthy(event: dict) -> bool:
    if event.get("primitive") == "REGIME_SHIFT":
        return True
    metric = event.get("metric", "")
    if _ID_PATTERN.search(metric):
        return False
    if _TEMPORAL_PATTERN.search(metric):
        return False
    if abs(event.get("magnitude_pct", 0.0)) < _MIN_MAGNITUDE_PCT:
        return False
    if event.get("zero_ratio", 0.0) > _SPARSE_ZERO_RATIO:
        return False
    evidence = event.get("evidence", {})
    mean = abs(evidence.get("baseline_mean", 1.0))
    std  = abs(evidence.get("baseline_std", 0.0))
    if mean > 0 and (std / mean) > _CV_IDENTIFIER_LIMIT:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SCORING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _avg_confidence(events: list[dict]) -> float:
    if not events:
        return 0.0
    return round(sum(e["confidence"] for e in events) / len(events), 3)


def _compute_impact(events: list[dict]) -> float:
    """cusum_peak / threshold ratio, auditable from evidence block."""
    ratios = []
    for e in events:
        ev = e.get("evidence", {})
        peak = abs(ev.get("cusum_peak", 0.0))
        thr  = abs(ev.get("threshold", 1.0))
        if thr > 0:
            ratios.append(min(peak / thr, 1.0))
    if not ratios:
        ratios = [min(abs(e.get("magnitude_pct", 0.0)), 1.0) for e in events]
    return round(sum(ratios) / len(ratios), 3) if ratios else 0.0


def _extract_metrics(events: list[dict]) -> list[str]:
    return sorted(set(e["metric"] for e in events))


def _priority(confidence: float, impact: float) -> str:
    score = confidence * impact
    if score >= 0.6:
        return "HIGH"
    if score >= 0.3:
        return "MEDIUM"
    return "LOW"


def _fingerprint(decision: dict) -> str:
    key = decision["type"] + "|" + "|".join(sorted(decision["signals"]))
    return hashlib.md5(key.encode()).hexdigest()[:10]


# ─────────────────────────────────────────────────────────────────────────────
# SEGMENT EXTRACTION HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _extract_segments(events: list[dict]) -> tuple[list[dict], str]:
    """Pick the top-deviating segment from events' segment_context.
    Returns (segments_list, text_phrase) for injection into the decision."""
    best = None
    for e in events:
        for s in (e.get("segment_context") or []):
            dev = abs(s.get("deviation", 0.0))
            if best is None or dev > abs(best.get("deviation", 0.0)):
                best = s
    if best is None:
        return [], ""
    segments_out = [
        {"dimension": best["dimension"], "value": best["value"], "deviation": best["deviation"]}
    ]
    dev_pct = round(abs(best["deviation"]) * 100)
    phrase = f", driven by {best['value']} in {best['dimension']} ({dev_pct}% deviation)"
    return segments_out, phrase


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN DETECTORS
# ─────────────────────────────────────────────────────────────────────────────

def _efficiency_gain(inp: list, out: list, val: list) -> dict | None:
    down = [e for e in inp if e["direction"] == "DOWNWARD"]
    up   = [e for e in out + val if e["direction"] == "UPWARD"]
    if not down or not up:
        return None
    used = down + up
    conf = _avg_confidence(used)
    imp  = _compute_impact(used)
    metrics = _extract_metrics(used)
    segs, seg_phrase = _extract_segments(used)
    return {
        "type":     "EFFICIENCY_GAIN",
        "title":    "Efficiency Is Improving",
        "summary":  (
            f"You are getting more output for less input. "
            f"{_fmt(inp, 'DOWNWARD')} are declining while "
            f"{_fmt(out+val, 'UPWARD')} are rising{seg_phrase}. "
            "This is a structural efficiency improvement."
        ),
        "decision": "Protect and reinvest in what is driving this efficiency.",
        "priority": _priority(conf, imp),
        "confidence": conf,
        "impact":   imp,
        "signals":  metrics,
        "segments": segs,
        "visualization": {"chart": "line", "x": "date", "y": metrics},
    }


def _demand_decline(inp: list, out: list) -> dict | None:
    declining = [e for e in inp + out if e["direction"] == "DOWNWARD"]
    if len(declining) < 2:
        return None
    conf = _avg_confidence(declining)
    imp  = _compute_impact(declining)
    metrics = _extract_metrics(declining)
    segs, seg_phrase = _extract_segments(declining)
    return {
        "type":     "DEMAND_DECLINE",
        "title":    "Demand Is Declining",
        "summary":  (
            f"{', '.join(metrics)} are all trending downward together{seg_phrase}. "
            "This is a broad demand signal, not an isolated metric movement."
        ),
        "decision": "Investigate whether this is market-wide or specific to a channel or product.",
        "priority": _priority(conf, imp),
        "confidence": conf,
        "impact":   imp,
        "signals":  metrics,
        "segments": segs,
        "visualization": {"chart": "line", "x": "date", "y": metrics},
    }


def _pricing_shift(val: list, cost: list) -> dict | None:
    up = [e for e in val + cost if e["direction"] == "UPWARD"]
    if len(up) < 2:
        return None
    conf = _avg_confidence(up)
    imp  = _compute_impact(up)
    metrics = _extract_metrics(up)
    segs, seg_phrase = _extract_segments(up)
    return {
        "type":     "PRICING_SHIFT",
        "title":    "Pricing Is Moving Up",
        "summary":  (
            f"{', '.join(metrics)} are rising consistently{seg_phrase}. "
            "Your pricing or monetization model is shifting upward."
        ),
        "decision": "Validate whether this is intentional pricing strategy or cost passthrough.",
        "priority": _priority(conf, imp),
        "confidence": conf,
        "impact":   imp,
        "signals":  metrics,
        "segments": segs,
        "visualization": {"chart": "line", "x": "date", "y": metrics},
    }


def _quality_deterioration(qual: list) -> dict | None:
    up = [e for e in qual if e["direction"] == "UPWARD"]
    if not up:
        return None
    conf = _avg_confidence(up)
    imp  = _compute_impact(up)
    metrics = _extract_metrics(up)
    segs, seg_phrase = _extract_segments(up)
    return {
        "type":     "QUALITY_DETERIORATION",
        "title":    "Quality or Risk Metrics Are Worsening",
        "summary":  (
            f"{', '.join(metrics)} are rising{seg_phrase} — these are risk or quality indicators. "
            "Rising values here mean things are getting worse."
        ),
        "decision": "Escalate to operations or quality team. Investigate root cause before it compounds.",
        # F-09: Quality uses same priority function with 1.5x amplifier
        "priority": _priority(conf, min(imp * 1.5, 1.0)),
        "confidence": conf,
        "impact":   imp,
        "signals":  metrics,
        "segments": segs,
        "visualization": {"chart": "line", "x": "date", "y": metrics},
    }


def _inventory_shift(trans: list) -> dict | None:
    if not trans:
        return None
    conf = _avg_confidence(trans)
    imp  = _compute_impact(trans)
    metrics = _extract_metrics(trans)
    directions = list({e["direction"] for e in trans})
    direction_str = directions[0].lower() if len(directions) == 1 else "shifting"
    segs, seg_phrase = _extract_segments(trans)
    return {
        "type":     "INVENTORY_SHIFT",
        "title":    "Supply Chain Movement Is Changing",
        "summary":  (
            f"Transfer and inventory metrics are trending {direction_str}{seg_phrase}. "
            "Stock movement patterns have shifted from historical norms."
        ),
        "decision": "Review warehouse capacity and reorder policies. Check for demand-supply mismatch.",
        "priority": _priority(conf, imp),
        "confidence": conf,
        "impact":   imp,
        "signals":  metrics,
        "segments": segs,
        "visualization": {"chart": "bar", "x": "date", "y": metrics},
    }


def _growth_signal(out: list, val: list) -> dict | None:
    """Fires when outputs AND value metrics are both rising — positive growth."""
    up_out = [e for e in out if e["direction"] == "UPWARD"]
    up_val = [e for e in val if e["direction"] == "UPWARD"]
    if not up_out or not up_val:
        return None
    used = up_out + up_val
    conf = _avg_confidence(used)
    imp  = _compute_impact(used)
    metrics = _extract_metrics(used)
    segs, seg_phrase = _extract_segments(used)
    return {
        "type":     "GROWTH_SIGNAL",
        "title":    "Growth Detected Across Key Metrics",
        "summary":  (
            f"Both output metrics ({_fmt(out, 'UPWARD')}) and value metrics "
            f"({_fmt(val, 'UPWARD')}) are rising together{seg_phrase}. "
            "This is a broad growth signal."
        ),
        "decision": "Identify the leading driver and double down. Protect the conditions enabling this growth.",
        "priority": _priority(conf, imp),
        "confidence": conf,
        "impact":   imp,
        "signals":  metrics,
        "segments": segs,
        "visualization": {"chart": "line", "x": "date", "y": metrics},
    }


def _funnel_breakdown(inp: list, out: list, val: list, qual: list) -> dict | None:
    """
    Detects inefficient funnel including conversion/quality drops
    """

    inputs_up = [e for e in inp if e["direction"] == "UPWARD"]
    
    outputs_down = [
        e for e in (out + qual)
        if e["direction"] == "DOWNWARD"
    ]

    value_up = [e for e in val if e["direction"] == "UPWARD"]

    if inputs_up and outputs_down:
        used = inputs_up + outputs_down
    elif value_up and outputs_down:
        used = value_up + outputs_down
    else:
        return None

    conf = _avg_confidence(used)
    imp  = _compute_impact(used)
    metrics = _extract_metrics(used)
    segs, seg_phrase = _extract_segments(used)

    return {
        "type": "FUNNEL_BREAKDOWN",
        "title": "Funnel Efficiency Is Degrading",
        "summary": f"Traffic or revenue is increasing but conversion/quality metrics are declining{seg_phrase}.",
        "decision": "Investigate funnel quality, targeting, or conversion bottlenecks.",
        "priority": _priority(conf, imp),
        "confidence": conf,
        "impact": imp,
        "signals": metrics,
        "segments": segs,
        "visualization": {"chart": "line", "x": "date", "y": metrics},
    }
def _concentration_risk(event: dict) -> dict | None:
    """
    F-01: Dedicated handler for STRUCTURAL (DOMINANCE) events.
    Describes concentration factually without claiming a temporal direction.
    Dominance is a structural property — it does NOT mean decline.
    """
    metric = event.get("metric", "Unknown")
    conf   = round(event.get("confidence", 0.4), 3)
    imp    = round(min(event.get("magnitude_pct", 0.2), 1.0), 3)
    primitive = event.get("primitive", "DOMINANCE")
    subtype = (event.get("evidence", {}).get("subtype")
               or event.get("subtype", "")
               or primitive).upper()

    segs, seg_phrase = _extract_segments([event])

    if subtype == "CATEGORICAL":
        desc = f"{metric} is concentrated in a single dominant category{seg_phrase}."
        title = f"{metric} Has High Categorical Concentration"
    elif subtype == "POINT":
        desc = f"{metric} is dominated by a single repeated value{seg_phrase}."
        title = f"{metric} Shows Point Dominance"
    elif subtype in ("RANGE_STD", "RANGE_QUANTILE"):
        desc = f"{metric} operates within an unusually tight range{seg_phrase}."
        title = f"{metric} Has a Constrained Operating Range"
    else:
        desc = f"{metric} exhibits structural concentration{seg_phrase}."
        title = f"{metric} Shows Structural Concentration"

    return {
        "type":       "CONCENTRATION_RISK",
        "title":      title,
        "summary":    (
            f"{desc} This is a structural property of the data — not a trend or decline. "
            "High concentration indicates dependency risk if the dominant segment shifts."
        ),
        "decision":   f"Assess whether concentration in {metric} represents acceptable risk or fragility.",
        "priority":   _priority(conf, imp),
        "confidence": conf,
        "impact":     imp,
        "signals":    [metric],
        "segments":   segs,
        "visualization": {"chart": "pie", "x": metric, "y": "share"},
    }


def _unknown_pattern(unknown: list) -> dict | None:
    """Produce a decision from UNKNOWN-role events that matched no named pattern."""
    if not unknown:
        return None
    top = sorted(unknown, key=lambda e: -e.get("magnitude_pct", 0.0))
    used = top[:2]
    conf = _avg_confidence(used)
    imp  = _compute_impact(used)
    metrics = _extract_metrics(used)
    direction = top[0].get("direction", "UNKNOWN")
    verb = "rising" if direction == "UPWARD" else "declining" if direction == "DOWNWARD" else "shifting"

    # Extract segment context from the top event
    seg_ctx = top[0].get("segment_context") or []
    top_seg = seg_ctx[0] if seg_ctx else None
    seg_phrase = ""
    if top_seg:
        dev_pct = round(abs(top_seg["deviation"]) * 100)
        seg_phrase = f", most prominently in {top_seg['value']} ({top_seg['dimension']}={dev_pct}% deviation)"
        # F-08: Removed confidence boost — all adjustments go through confidence_engine

    summary = (
        f"{metrics[0]} is {verb}{seg_phrase}. "
        "This signal does not match standard business patterns. "
        "Investigate whether this reflects an operational or market change."
    )
    segments_out = [
        {"dimension": s["dimension"], "value": s["value"], "deviation": s["deviation"]}
        for s in seg_ctx[:3]
    ]
    return {
        "type":       "STRUCTURAL_CHANGE",
        "title":      f"{metrics[0]} Is {verb.title()}{(', Led by ' + top_seg['value']) if top_seg else ''}",
        "summary":    summary,
        "decision":   "Monitor this metric closely and investigate root cause.",
        "priority":   _priority(conf, imp),
        "confidence": round(conf, 3),
        "impact":     imp,
        "signals":    metrics,
        "segments":   segments_out,
        "visualization": {"chart": "line", "x": "date", "y": metrics},
    }


def _direct_event_decision(event: dict) -> dict:
    """Convert a single event directly into a minimal valid decision."""
    metric    = event.get("metric", "Unknown")
    direction = event.get("direction", "UNKNOWN")
    primitive = event.get("primitive", "SIGNAL")
    conf      = round(event.get("confidence", 0.4), 3)
    imp       = round(min(event.get("magnitude_pct", 0.2), 1.0), 3)
    verb      = "rising" if direction == "UPWARD" else "declining" if direction == "DOWNWARD" else "shifting"

    # Extract segment context
    seg_ctx = event.get("segment_context") or []
    top_seg = seg_ctx[0] if seg_ctx else None
    seg_phrase = ""
    if top_seg:
        dev_pct = round(abs(top_seg["deviation"]) * 100)
        seg_phrase = f", driven by {top_seg['value']} ({top_seg['dimension']}={dev_pct}% deviation)"
        # F-08: Removed confidence boost — all adjustments go through confidence_engine

    segments_out = [
        {"dimension": s["dimension"], "value": s["value"], "deviation": s["deviation"]}
        for s in seg_ctx[:3]
    ]

    if primitive == "TRADEOFF":
        metrics = event.get("metrics", [metric])
        pair_class = event.get("pair_classification", "UNKNOWN")
        corr = event.get("evidence", {}).get("correlation", 0)
        corr_str = f"{abs(corr):.0%}" if corr else ""

        if pair_class == "TRUE_TRADEOFF":
            title = f"Structural Tradeoff: {', '.join(metrics[:2])}"
            summary = (
                f"{metrics[0]} and {metrics[1]} are positively correlated ({corr_str}) "
                f"despite having opposing economic polarities{seg_phrase}. "
                f"Improving one structurally coincides with worsening the other."
            )
            decision = f"Assess whether the {metrics[0]}–{metrics[1]} tradeoff is acceptable or requires rebalancing."
        elif pair_class == "CONFLICT":
            title = f"Metric Conflict: {', '.join(metrics[:2])}"
            summary = (
                f"{metrics[0]} and {metrics[1]} are moving in opposite directions ({corr_str} inverse correlation) "
                f"despite sharing the same economic polarity{seg_phrase}. "
                f"These metrics should co-move but are diverging."
            )
            decision = f"Investigate why {metrics[0]} and {metrics[1]} are diverging — this may indicate a process breakdown."
        else:
            title = f"Correlated Metrics: {', '.join(metrics[:2])}"
            summary = (
                f"A statistically significant relationship exists between "
                f"{metrics[0]} and {metrics[1]} ({corr_str} correlation){seg_phrase}. "
                f"Economic polarity could not be determined — review whether this is expected."
            )
            decision = f"Review the relationship between {', '.join(metrics[:2])} to determine if action is needed."

        return {
            "type":       "TRADEOFF",
            "title":      title,
            "summary":    summary,
            "decision":   decision,
            "priority":   _priority(conf, imp),
            "confidence": conf,
            "impact":     imp,
            "signals":    metrics,
            "segments":   segments_out,
            "pair_classification": pair_class,
            "visualization": {"chart": "scatter", "x": metrics[0], "y": metrics[1] if len(metrics) > 1 else metrics[0]},
        }

    if primitive == "REGIME_SHIFT" and event.get("metrics"):
        metrics = event["metrics"]
        if len(metrics) >= 2:
            driver = metrics[0]
            outcome = metrics[1]
            
            signal_score = event.get("signal_score", 0.0)
            if signal_score > 0.85:
                reg_priority = "HIGH"
            elif signal_score > 0.7:
                reg_priority = "MEDIUM"
            else:
                reg_priority = "LOW"

            # Direction from actual_change (correctness layer) — NOT correlation
            actual_change = event.get("correctness", {}).get("actual_change", 0)
            if actual_change > 0.02:
                regime_direction = "UPWARD"
            elif actual_change < -0.02:
                regime_direction = "DOWNWARD"
            else:
                regime_direction = "FLAT"
            METRIC_ROLE_MAP = {
                "tacos": "COST", "cac": "COST", "cpa": "COST", "cost": "COST", "spend": "COST",
                "revenue": "REVENUE", "sales": "REVENUE", "gmv": "REVENUE",
                "roas": "VALUE", "roi": "VALUE", "aov": "VALUE", "conversion_rate": "VALUE", "ctr": "VALUE"
            }
            metric_name = outcome.lower().replace(" ", "_")
            role = METRIC_ROLE_MAP.get(metric_name)
            if role is None:
                if any(k in metric_name for k in ["cost", "cpa", "tacos", "churn", "expense", "burn"]):
                    role = "COST"
                elif any(k in metric_name for k in ["revenue", "sales", "profit", "gmv"]):
                    role = "REVENUE"
                elif any(k in metric_name for k in ["roas", "roi", "ctr", "conversion", "aov"]):
                    role = "VALUE"
                else:
                    role = "UNKNOWN"

            driver_role = event.get("role", "UNKNOWN")
            conflict = (driver_role == "INPUT" and regime_direction == "DOWNWARD")

            if role == "COST" and regime_direction == "UPWARD":
                reg_priority = "CRITICAL"
                reg_summary = f"{outcome} is increasing with higher {driver}, indicating declining efficiency."
                reg_title = f"{outcome} Efficiency Decline vs {driver}"
                reg_decision = (
                    f"CRITICAL: {outcome} is rising with {driver}. "
                    f"This indicates efficiency breakdown. Pause scaling and fix immediately."
                )
            else:
                if conflict:
                    reg_summary = f"{outcome} is declining despite increasing {driver}. This indicates diminishing efficiency."
                    reg_title = f"{outcome} Diminishing Returns vs {driver}"
                    reg_decision = (
                        f"WARNING: Increasing {driver} is negatively impacting {outcome}. "
                        f"Re-evaluate allocation and optimize efficiency before scaling further."
                    )
                elif regime_direction == "DOWNWARD":
                    reg_summary = f"{outcome} is declining, but highly dependent on {driver}. Reversing the drop in {driver} is the primary lever to improve {outcome}."
                    reg_title = f"{outcome} Declining (Driven by {driver})"
                elif regime_direction == "UPWARD":
                    reg_summary = f"{outcome} is increasing, strongly driven by growth in {driver}. Increasing {driver} remains the primary lever to accelerate {outcome}."
                    reg_title = f"{outcome} Growth (Driven by {driver})"
                else:
                    reg_summary = f"{outcome} is currently stable but highly dependent on {driver}. Optimizing {driver} is the primary lever to improve {outcome}."
                    reg_title = f"{outcome} Stability Dependent on {driver}"
                    
                if not conflict:
                    reg_decision = (
                        f"Focus on optimizing {driver} as the primary lever to improve {outcome}. "
                        f"Prioritize actions that directly impact {driver} such as pricing strategy, "
                        f"campaign optimization, or operational adjustments."
                    )
                    if signal_score > 0.9:
                        reg_decision += " This is a dominant driver relationship and should be prioritized immediately."
                
            return {
                "type": "REGIME_SHIFT",
                "title": reg_title,
                "summary": reg_summary,
                "decision": reg_decision,
                "priority": reg_priority,
                "confidence": conf,
                "impact": imp,
                "signals": metrics,
                "segments": segments_out,
                "drivers": [driver],
                "visualization": {"chart": "line", "x": "date", "y": metrics},
            }
    final_priority = "LOW" if conf < 0.7 else _priority(conf, imp)

    # ── Magnitude sanity override ────────────────────────────────────
    # Large real-world changes (>30%) must never be labeled "normal variation"
    # even when confidence is low (e.g., from maturity penalty on first upload).
    # An 80% shift is structurally significant regardless of statistical confidence.
    actual_change = abs(event.get("actual_change", 0.0))
    if actual_change > 0.30 and final_priority == "LOW":
        final_priority = "MEDIUM"

    # ── Calibrate language to signal strength ────────────────────────
    # HIGH: strong, actionable language
    # MEDIUM: cautious, monitoring language
    # LOW: informational, no urgency
    change_pct = f"{round(actual_change * 100, 1)}%"

    if final_priority == "HIGH":
        summary = (
            f"{metric} is {verb} with a {change_pct} change from baseline{seg_phrase}. "
            f"This is a significant structural shift detected by {primitive.lower()} analysis."
        )
        decision = f"Prioritize review of {metric} — this movement exceeds normal operating range."
    elif final_priority == "MEDIUM":
        summary = (
            f"{metric} shows a moderate {verb} trend ({change_pct} change){seg_phrase}. "
            f"The pattern is statistically detectable but may not yet require intervention."
        )
        decision = f"Monitor {metric} for persistence. If the trend continues, investigate root cause."
    else:
        summary = (
            f"{metric} has shifted slightly ({change_pct} change){seg_phrase}. "
            f"The movement is within a range that may reflect normal variation."
        )
        decision = f"No immediate action needed. Continue monitoring {metric} for further development."

    return {
        "type":       "METRIC_ALERT",
        "title":      f"{metric} Is {verb.title()}{(', Led by ' + top_seg['value']) if top_seg else ''}",
        "summary":    summary,
        "decision":   decision,
        "priority":   final_priority,
        "confidence": conf,
        "impact":     imp,
        "signals":    [metric],
        "segments":   segments_out,
        "visualization": {"chart": "line", "x": "date", "y": [metric]},
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SYNTHESIZER
# ─────────────────────────────────────────────────────────────────────────────

def synthesize_decisions(
    events: list[dict[str, Any]],
    *,
    ordered_data: bool = False,
    enrich: bool = False,
) -> list[dict[str, Any]]:
    """
    Convert validated events into up to 3 business decisions.

    Args:
        events:       normalized events from event_engine.normalize_events()
        ordered_data: True if source data was time-ordered
        enrich:       if True, run domain-agnostic enrichment pass to attach
                      FACT / PATTERN / IMPACT / ACTION / HYPOTHESIS blocks
                      to every decision via decision_enricher.enrich_decisions()

    Returns:
        Deterministic list of 0–3 decisions with title, summary, priority.
        Returns [] when no pattern meets the quality bar.
    """
    if not events:
        return []

    # ── Validate signals ────────────────────────────────────────────────
    valid = [e for e in events if _is_trustworthy(e) and e.get("confidence", 0) >= 0.30]

    if not ordered_data:
        # Penalise BIAS signals from unordered data
        penalised = []
        for e in valid:
            if e.get("primitive") == "BIAS":
                e = {**e, "confidence": round(e["confidence"] * _UNORDERED_BIAS_PENALTY, 4)}
            penalised.append(e)
        valid = penalised

    if not valid:
        return []

    # ── Apply validated_direction as single source of truth ─────────
    # correctness_layer sets validated_direction when it overrides.
    # Normalise here so all downstream code reads event["direction"].
    resolved: list[dict] = []
    for e in valid:
        vdir = e.get("validated_direction")
        if vdir and vdir != e.get("direction"):
            e = {**e, "direction": vdir}
        resolved.append(e)
    valid = resolved

    # ── FLAT suppression: validated_direction=FLAT means actual change ≈ 0.
    # Generating decisions from these produces contradictions ("shifting"
    # for a metric that isn't moving). TRADEOFF/STRUCTURAL are exempt
    # because they don't claim temporal direction.
    valid = [
        e for e in valid
        if e.get("validated_direction") != "FLAT"
        or e.get("primitive") in ("TRADEOFF", "REGIME_SHIFT")
        or e.get("direction") == "STRUCTURAL"
    ]

    # ── Impact gate: suppress marginal signals that technically passed
    # all gates but have negligible real-world impact.
    # actual_change < 5% AND magnitude_pct < 10% → not decision-worthy.
    _MIN_IMPACT_CHANGE = 0.05
    _MIN_IMPACT_MAGNITUDE = 0.10
    valid = [
        e for e in valid
        if (
            abs(e.get("actual_change", 1.0)) >= _MIN_IMPACT_CHANGE
            or e.get("magnitude_pct", 1.0) >= _MIN_IMPACT_MAGNITUDE
            or e.get("direction") == "STRUCTURAL"
            or e.get("primitive") in ("TRADEOFF", "REGIME_SHIFT")
        )
    ]

    if not valid:
        return []

    # ── Run detectors ───────────────────────────────────────────────────
    candidates: list[dict] = []

    # ── FORCE REGIME_SHIFT + TRADEOFF HANDLING FIRST ─────────────────────
    # These primitives have dedicated handlers in _direct_event_decision()
    # and must be routed there before role-based grouping.
    remaining_valid = []
    for event in valid:
        if event.get("primitive") in ("REGIME_SHIFT", "TRADEOFF"):
            decision = _direct_event_decision(event)
            if decision:
                candidates.append(decision)
            continue
        remaining_valid.append(event)
    valid = remaining_valid

    # ── F-01: STRUCTURAL (DOMINANCE) HANDLING ──────────────────────────
    # Dominance signals are non-directional — they describe concentration,
    # not temporal decline. Route them to CONCENTRATION_RISK before
    # role-based grouping to prevent false DEMAND_DECLINE decisions.
    structural_remaining = []
    for event in valid:
        if event.get("direction") == "STRUCTURAL":
            decision = _concentration_risk(event)
            if decision:
                candidates.append(decision)
            continue
        structural_remaining.append(event)
    valid = structural_remaining

    # ── Group by role ───────────────────────────────────────────────────
    groups: dict[str, list] = {
        r: [] for r in ("INPUT", "OUTPUT", "VALUE", "COST", "QUALITY", "TRANSFER", "UNKNOWN")
    }
    for e in valid:
        groups[e.get("role", "UNKNOWN")].append(e)

    for fn in [
    lambda: _efficiency_gain(groups["INPUT"], groups["OUTPUT"], groups["VALUE"]),
    lambda: _growth_signal(groups["OUTPUT"], groups["VALUE"]),
    lambda: _demand_decline(groups["INPUT"], groups["OUTPUT"]),
    lambda: _pricing_shift(groups["VALUE"], groups["COST"]),
    lambda: _funnel_breakdown(groups["INPUT"], groups["OUTPUT"], groups["VALUE"],groups["QUALITY"]),  # ✅ NEW
    lambda: _quality_deterioration(groups["QUALITY"]),
    lambda: _inventory_shift(groups["TRANSFER"]),
]:
        try:
            result = fn()
            if result:
                candidates.append(result)
        except Exception:
            continue

    # ── Fallback 1: UNKNOWN-role events that matched no named pattern ───
    if not candidates:
        unk = _unknown_pattern(groups["UNKNOWN"])
        if unk:
            candidates.append(unk)

    # ── Fallback 2: direct-convert top events by magnitude ───────────────
    if not candidates:
        top_events = sorted(
            valid, key=lambda e: -e.get("magnitude_pct", 0.0) * e.get("confidence", 0.0)
        )
        seen_metrics: set[str] = set()
        for ev in top_events:
            m = ev.get("metric", "")
            if m not in seen_metrics:
                candidates.append(_direct_event_decision(ev))
                seen_metrics.add(m)
            if len(candidates) >= _MAX_DECISIONS:
                break

    # ── Deduplicate ─────────────────────────────────────────────────────
    seen_fps: set[str] = set()
    deduped: list[dict] = []
    for d in candidates:
        fp = _fingerprint(d)
        if fp not in seen_fps:
            seen_fps.add(fp)
            deduped.append(d)

    # ── Sort: impact*confidence desc, type asc (deterministic tiebreaker) ─
    deduped.sort(
        key=lambda d: (-round(d["impact"] * d["confidence"], 6), d["type"])
    )

    result = deduped[:_MAX_DECISIONS]

    # ── Fill to 3 with signal-driven supporting decisions ───────────────────
    # Always runs when result < 3 — uses remaining valid events not already
    # covered. Never produces STABLE/generic text when real signals exist.
    if len(result) < _MAX_DECISIONS and valid:
        # Collect metrics already represented in result
        covered_metrics: set[str] = set()
        for d in result:
            for s in d.get("signals", []):
                covered_metrics.add(s.lower())

        # Sort remaining events by magnitude*confidence desc (deterministic)
        remaining = sorted(
            [e for e in valid if e.get("metric", "").lower() not in covered_metrics],
            key=lambda e: (
                -e.get("magnitude_pct", 0.0) * e.get("confidence", 0.0),
                e.get("metric", ""),
            ),
        )

        seen_support: set[str] = set()
        for ev in remaining:
            if len(result) >= _MAX_DECISIONS:
                break
            m = ev.get("metric", "")
            if not m or m.lower() in seen_support:
                continue
            seen_support.add(m.lower())
            result.append(_direct_event_decision(ev))

        # Context-alignment slot: if still short, describe signal agreement
        if len(result) < _MAX_DECISIONS and result:
            primary = result[0]
            p_signals = primary.get("signals", [])
            all_dirs = {e.get("direction") for e in valid}
            all_same_dir = len(all_dirs) == 1 and all_dirs != {""}
            ctx_summary = (
                f"All detected signals are aligned in the same direction, "
                f"reinforcing the primary finding in {', '.join(p_signals[:2])}. "
                "No conflicting trends detected across the monitored metrics."
            ) if all_same_dir else (
                f"Mixed directional signals detected across metrics. "
                f"The primary trend in {', '.join(p_signals[:2])} is accompanied by "
                "diverging movements in secondary metrics — investigate for structural causes."
            )
            segs, _ = _extract_segments(valid)
            result.append({
                "type":       "SIGNAL_CONTEXT",
                "title":      "Signal Alignment Across Metrics",
                "summary":    ctx_summary,
                "decision":   (
                    "Validate the primary trend against segment-level data. "
                    "Check whether the movement is concentrated or broad-based."
                ),
                "priority":   _priority(
                    primary.get("confidence", 0.3), primary.get("impact", 0.2)
                ),
                "confidence": round(primary.get("confidence", 0.3) * 0.85, 3),
                "impact":     round(primary.get("impact", 0.2) * 0.7, 3),
                "signals":    _extract_metrics(valid),
                "segments":   segs,
                "visualization": {"chart": "summary", "x": "metric", "y": "direction"},
            })

    # ── Optional enrichment pass ────────────────────────────────────────────
    if enrich and result:
        result = enrich_decisions(result, valid)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS (used by routes.py)
# ─────────────────────────────────────────────────────────────────────────────

def deduplicate_semantic_mappings(mappings: dict[str, str]) -> dict[str, str]:
    """
    Resolve semantic mapping collisions.
    First occurrence wins; subsequent collisions are suffixed _2, _3 etc.
    """
    seen: dict[str, int] = {}
    resolved: dict[str, str] = {}
    for original, canonical in mappings.items():
        if canonical not in seen:
            seen[canonical] = 1
            resolved[original] = canonical
        else:
            seen[canonical] += 1
            resolved[original] = f"{canonical}_{seen[canonical]}"
    return resolved


def detect_composite_timestamp(
    df_columns: list[str],
) -> tuple[str | None, str | None]:
    """
    Detect YEAR + MONTH (or YEAR + QUARTER) as composite temporal index.
    Returns (year_col, month_col) or (None, None).
    """
    cols_lower = {c.strip().lower(): c for c in df_columns}

    year_col = next(
        (cols_lower[c] for c in cols_lower
         if re.fullmatch(r"year|yr|fiscal_year|fy", c)),
        None,
    )
    month_col = next(
        (cols_lower[c] for c in cols_lower
         if re.fullmatch(r"month|mo|mth", c)),
        None,
    )
    quarter_col = next(
        (cols_lower[c] for c in cols_lower
         if re.fullmatch(r"quarter|qtr|q", c)),
        None,
    )

    if year_col:
        return year_col, month_col or quarter_col
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL FORMATTING HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(events: list[dict], direction: str) -> str:
    """Format metric names from a filtered event list into readable string."""
    names = sorted(set(
        e["metric"] for e in events if e.get("direction") == direction
    ))
    if not names:
        return "some metrics"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"