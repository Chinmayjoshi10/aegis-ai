"""
aegis_ai/core/decision_pipeline.py
=====================================
Decision Pipeline — full orchestration from brain insights to validated decisions.

Flow:
  normalize_events
  → synthesize_decisions
  → validate_decisions
  → return structured output

Called by routes.py after run_company_brain_v2().

Args accepted:
  company_insights:  list of insight dicts from brain_output["insights"]
  tenant_id:         str
  ordered_data:      bool  — True if data had a real time column
  reality_snapshot:  dict  — {"numeric": {metric: stats}}
  df:                pd.DataFrame | None — needed for validation
  time_column:       str | None — for temporal validation split
  baseline_stats:    dict | None — fallback if reality_snapshot is absent

Returns:
  {
    "decisions":     list of validated decision dicts (with consistency field)
    "decision_meta": {input_signals, filtered_events, decisions_generated, decisions_after_validation}
  }
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aegis_ai.core.data_understanding_layer import DataUnderstandingLayer

log = logging.getLogger("aegis_ai.core.decision_pipeline")

DataUnderstanding = dict[str, list[Any]]


def _map_decision_to_signal_type(decision_type: str) -> str:
    """Map decision type back to root signal type for sellable output."""
    _MAP = {
        "EFFICIENCY_GAIN": "BIAS",
        "DEMAND_DECLINE": "BIAS",
        "PRICING_SHIFT": "BIAS",
        "QUALITY_DETERIORATION": "BIAS",
        "GROWTH_SIGNAL": "BIAS",
        "FUNNEL_BREAKDOWN": "BIAS",
        "INVENTORY_SHIFT": "BIAS",
        "METRIC_ALERT": "BIAS",
        "CONCENTRATION_RISK": "DOMINANCE",
        "REGIME_SHIFT": "BIAS",
        "TRADEOFF": "TRADEOFF",
        "STRUCTURAL_CHANGE": "UNKNOWN",
        "SIGNAL_CONTEXT": "CONTEXT",
    }
    return _MAP.get(decision_type, "UNKNOWN")


def run_decision_pipeline(
    company_insights: list[dict[str, Any]],
    tenant_id: str,
    *,
    ordered_data: bool = False,
    reality_snapshot: dict[str, Any] | None = None,
    df: pd.DataFrame | None = None,
    time_column: str | None = None,
    baseline_stats: dict[str, Any] | None = None,
    valid_metrics: list[str] | None = None,
    metric_roles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Full decision pipeline: normalize → synthesize → validate.
    Fail-open at every stage.
    """
    from aegis_ai.core.event_engine import normalize_events
    from aegis_ai.company_brain.decision_synthesizer import synthesize_decisions
    from aegis_ai.core.decision_validator import validate_decisions

    reality = reality_snapshot or {}
    stats   = baseline_stats or reality.get("numeric", {})

    empty_decisions: list[dict[str, Any]] = []

    meta: dict[str, Any] = {
        "input_signals":               len(company_insights),
        "filtered_events":             0,
        "normalized_events":           0,
        "key_metric_filtered_events":  0,
        "decisions_generated":         0,
        "decisions_after_validation":  0,
        "ordered_data":                ordered_data,
        "tenant_id":                   tenant_id,
    }

    # ── Step 1: Normalize events ────────────────────────────────────────
    events: list[dict[str, Any]] = []

    try:
        events = normalize_events(
            company_insights,
            reality,
            ordered_data=ordered_data,
            metric_roles=metric_roles,
        )
        meta["normalized_events"] = len(events)
        meta["filtered_events"] = len(events)
    except Exception as e:
        log.error(f"[PIPELINE] normalize_events failed: {e}", exc_info=True)
        return {"decisions": empty_decisions, "decision_meta": meta}

    if not events:
        return {
            "decisions": empty_decisions,
            "status": "NO_SIGNIFICANT_CHANGE",
            "message": "No meaningful structural changes detected in the dataset",
            "decision_meta": meta,
        }

    # ── Step 1b: Correctness Layer ──────────────────────────────────────
    # Validates direction against actual data, rejects identifiers,
    # annotates signed metrics. Must run BEFORE synthesis.
    data_understanding: DataUnderstanding = {
        "key_metrics": [],
        "important_dimensions": [],
        "relationships": [],
    }

    if df is not None and not df.empty:
        try:
            from aegis_ai.core.correctness_layer import validate_signals
            pre_count = len(events)
            events = validate_signals(events, df, stats, time_column=time_column, valid_metrics=valid_metrics)
            meta["correctness_rejected"] = pre_count - len(events)
            meta["correctness_validated"] = len(events)
            meta["filtered_events"] = len(events)
        except Exception as e:
            log.error(f"[PIPELINE] correctness_layer failed: {e}", exc_info=True)
            # Fail-open — continue with unvalidated events
            meta["correctness_error"] = str(e)

        try:
            data_understanding = DataUnderstandingLayer().run(df)
            meta["data_understanding_key_metrics"] = len(
                data_understanding.get("key_metrics", [])
            )
        except Exception as e:
            log.error(f"[PIPELINE] data_understanding_layer failed: {e}", exc_info=True)
            meta["data_understanding_error"] = str(e)

    if not events:
        return {
            "decisions": empty_decisions,
            "status": "NO_SIGNIFICANT_CHANGE",
            "message": "All signals rejected by correctness validation",
            "decision_meta": meta,
        }

    # ── Step 2: Synthesize decisions ────────────────────────────────────
    decisions: list[dict[str, Any]] = []
    try:
        key_metrics = [
            metric for metric in data_understanding.get("key_metrics", [])
            if isinstance(metric, str)
        ]
        events_for_synthesis = events
        if key_metrics:
            key_metric_set = set(key_metrics)
            
            # 1. Scoring
            for e in events:
                base_score = e.get("signal_score", 0.0)
                if e.get("primitive") == "REGIME_SHIFT":
                    base_score += 0.5   # stronger boost
                elif e.get("primitive") == "BIAS":
                    base_score -= 0.2   # reduce dominance
                e["priority_score"] = base_score

            # 2. Filtering
            filtered_events = [
                e for e in events
                if (
                    e.get("metric") in key_metric_set
                    or e.get("primitive") in ("TRADEOFF", "REGIME_SHIFT")
                )
            ]

            # 3. Sorting
            prim_weights = {"REGIME_SHIFT": 3, "DOMINANCE": 2, "BIAS": 1}
            filtered_events.sort(
                key=lambda x: (
                    prim_weights.get(x.get("primitive", ""), 0),
                    x.get("priority_score", 0.0),
                    x.get("confidence", 0.0)
                ),
                reverse=True
            )

            # 4. Force include top 1 REGIME_SHIFT if missed
            top_regime = max(
                [e for e in events if e.get("primitive") == "REGIME_SHIFT"],
                key=lambda x: x.get("signal_score", 0),
                default=None
            )
            if top_regime and top_regime not in filtered_events[:3]:
                if top_regime in filtered_events:
                    filtered_events.remove(top_regime)
                filtered_events.insert(0, top_regime)

            meta["key_metric_filtered_events"] = len(filtered_events)
            if filtered_events:
                events_for_synthesis = filtered_events
                meta["filtered_events"] = len(events_for_synthesis)
            else:
                meta["key_metric_filter_skipped"] = "no_event_metric_overlap"
        decisions = synthesize_decisions(events_for_synthesis, ordered_data=ordered_data)
        meta["decisions_generated"] = len(decisions)
    except Exception as e:
        log.error(f"[PIPELINE] synthesize_decisions failed: {e}", exc_info=True)
        return {"decisions": empty_decisions, "decision_meta": meta}

    if not decisions:
        return {
            "decisions": empty_decisions,
            "status": "NO_SIGNIFICANT_CHANGE",
            "message": "No actionable decisions derived from current signals",
            "decision_meta": meta,
        }
    # ── Step 3: Validate decisions ──────────────────────────────────────
    if df is not None and not df.empty and stats:
        try:
            decisions = validate_decisions(
                decisions,
                df=df,
                baseline_stats=stats,
                ordered_data=ordered_data,
                time_column=time_column,
            )
        except Exception as e:
            log.error(f"[PIPELINE] validate_decisions failed: {e}", exc_info=True)
            # Fail-open — return unvalidated decisions with warning
            for d in decisions:
                d.setdefault("consistency", 1.0)
                d["validation_warning"] = f"validator_error: {e}"
    else:
        # No df provided — skip validation, mark as unvalidated
        for d in decisions:
            d.setdefault("consistency", 1.0)
            d["validation_note"] = "skipped_no_df"

    meta["decisions_after_validation"] = len(decisions)

    # ── Step 4: SELLABLE DECISION OUTPUT (Phase 5) ────────────────────
    # Each decision gets 5 required elements:
    #   1. Clear statement (what is happening)
    #   2. Directional meaning (improvement / deterioration / structural risk)
    #   3. Root signal type (BIAS / DOMINANCE / TRADEOFF)
    #   4. Confidence explanation (why high/medium/low)
    #   5. Business implication (what this indicates — NOT recommendations)
    for d in decisions:
        # Preserve numeric impact as impact_score
        raw_impact = d.get("impact")
        if isinstance(raw_impact, (int, float)):
            d["impact_score"] = round(raw_impact, 4)

        sigs = d.get("signals", [])
        segs = d.get("segments", [])
        conf = d.get("confidence", 0.0)
        dtype = d.get("type", "UNKNOWN")

        # 1. Clear statement
        d["fact"] = d.get("title", "A signal was detected.")

        # 2. Directional meaning (from economic_interpretation if available)
        econ = d.get("economic_interpretation", {})
        d["directional_meaning"] = econ.get("meaning", "change")

        # 3. Root signal type
        d["root_signal_type"] = _map_decision_to_signal_type(dtype)

        # 4. Confidence explanation
        if conf >= 0.85:
            conf_why = f"High confidence ({conf:.0%}) — strong signal score and sufficient data volume"
        elif conf >= 0.6:
            conf_why = f"Moderate confidence ({conf:.0%}) — signal detected but may lack temporal confirmation"
        elif conf >= 0.4:
            conf_why = f"Low confidence ({conf:.0%}) — limited evidence or immature baseline"
        else:
            conf_why = f"Very low confidence ({conf:.0%}) — preliminary signal, insufficient for action"
        d["confidence_explanation"] = conf_why

        # 5. Business implication (interpretation, NOT recommendation)
        seg_str = ""
        if segs and isinstance(segs[0], dict):
            top_seg = segs[0]
            dev_pct = round(abs(top_seg.get("deviation", 0.0)) * 100)
            seg_str = f", concentrated in {top_seg.get('value', '?')} ({top_seg.get('dimension', '?')}, {dev_pct}% deviation)"

        metric_str = ", ".join(sigs[:2]) if sigs else "the metric"
        meaning = econ.get("economic_label", "structural change")
        d["business_implication"] = (
            f"This indicates {meaning} in {metric_str}{seg_str}."
        )

        # Build impact string
        impact_parts = []
        if sigs:
            impact_parts.append(f"Affects {', '.join(sigs[:3])}")
        if segs:
            seg_strs = [
                f"{s.get('dimension','?')}={s.get('value','?')}"
                for s in segs[:2] if isinstance(s, dict)
            ]
            if seg_strs:
                impact_parts.append(f"concentrated in {', '.join(seg_strs)}")
        d["impact"] = ". ".join(impact_parts) + "." if impact_parts else "Broad impact across the dataset."

        d["pattern"] = d.get("summary", "")


    return {
        "decisions":        decisions,
        "decision_meta":    meta,
        "validated_events": events,   # corrected signals — routes replaces brain_output["insights"]
    }

