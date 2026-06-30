"""
aegis_ai/core/structured_output.py
====================================
Universal Structured Output — maps existing pipeline outputs into a single
canonical JSON schema for downstream consumers (UI, chatbot, narration, export).

Design:
  - Pure transformation layer: NO business logic, NO data access.
  - Reads only from already-computed pipeline outputs.
  - Deterministic: same inputs → same output every time.
  - Additive: does not replace or modify any existing response keys.

Schema v1.0.0:
  meta, state, state_reason, headline, confidence, signals, data_quality,
  dimension_analysis, decisions, root_cause, explainability,
  action, assumptions, limitations

Future:
  - This output is the sole input to the narration layer and chatbot.
  - When LLM narration is added, this schema is the contract.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from aegis_ai import __version__ as _aegis_version

log = logging.getLogger("aegis_ai.core.structured_output")

SCHEMA_VERSION = "1.0.0"

# ─────────────────────────────────────────────────────────────────────────────
# DIRECTION ENUM — locked canonical values
# ─────────────────────────────────────────────────────────────────────────────

_DIRECTION_MAP = {
    "UPWARD":     "UP",
    "DOWNWARD":   "DOWN",
    "STRUCTURAL": "STRUCTURAL",
    "FLAT":       "FLAT",
    "STABLE":     "FLAT",
    "NONE":       "FLAT",
}


def _normalize_direction(raw: str) -> str:
    """Normalize pipeline direction to canonical enum {UP, DOWN, FLAT, STRUCTURAL}."""
    return _DIRECTION_MAP.get(raw.upper(), "FLAT") if raw else "FLAT"


# Words that imply motion — must not appear in a FLAT signal's summary.
_MOTION_WORDS = (
    "drifting", "drift",
    "increasing", "increase",
    "decreasing", "decrease",
    "rising", "rise",
    "falling", "fall",
    "declining", "decline",
    "trending upward", "trending downward",
    "trending up", "trending down",
)

# Signal-score ceiling when direction == FLAT (per AEGIS semantic contract).
_FLAT_SIGNAL_SCORE_CEILING = 0.20


def _human_signal_summary(
    metric: str, direction: str, magnitude_pct: float, primitive: str
) -> str:
    """
    R2: emit a short, human-readable, direction-matched summary.
    Format: "{metric} {verb} by {magnitude}% vs baseline"
    """
    metric = metric or "Metric"
    verb_map = {
        "UP":         "rose",
        "DOWN":       "fell",
        "STRUCTURAL": "shows a structural pattern",
        "FLAT":       "is stable",
    }
    verb = verb_map.get(direction, "changed")
    if direction == "FLAT":
        return (
            f"{metric} is stable — no significant movement "
            f"relative to its historical baseline."
        )
    if direction == "STRUCTURAL":
        if primitive == "DOMINANCE":
            return f"{metric} shows structural concentration."
        if primitive == "TRADEOFF":
            return f"{metric} is part of a structural tradeoff."
        return f"{metric} shows a structural pattern."
    mag_str = (
        f" by {min(abs(magnitude_pct), 200.0):.1f}%"
        if magnitude_pct else ""
    )
    return f"{metric} {verb}{mag_str} vs baseline."


def _reconcile_flat_signal(sig: dict[str, Any]) -> dict[str, Any]:
    """
    Enforce semantic consistency for FLAT signals.

    Rules (signal-level only — does NOT alter mathematical outputs of detectors):
      1. FLAT summaries MUST NOT contain motion words ("drifting", etc).
      2. FLAT signal_score MUST be low (0.0 – 0.20); never 1.0.
      3. FLAT primitive MUST NOT be "BIAS" (BIAS ≡ structural drift). Coerce
         to "STABLE" unless the primitive is relational ("TRADEOFF") or
         concentration-based ("DOMINANCE"), which are direction-agnostic.
      4. Confidence is split into two calibrated views:
           - signal_confidence    → confidence THAT there is a change (low for FLAT)
           - stability_confidence → confidence THAT there is NO change (high for FLAT)
         The top-level `confidence` field is preserved for back-compat.
    """
    if sig.get("direction") != "FLAT":
        # Non-FLAT: calibration mirrors the engine's confidence on the signal.
        raw_conf = float(sig.get("confidence", 0.0))
        sig["signal_confidence"]    = round(raw_conf, 4)
        sig["stability_confidence"] = round(max(0.0, 1.0 - raw_conf), 4)
        return sig

    # ── Rule 2: cap signal_score ──────────────────────────────────────────
    score = float(sig.get("signal_score", 0.0))
    if score > _FLAT_SIGNAL_SCORE_CEILING:
        sig["signal_score"] = _FLAT_SIGNAL_SCORE_CEILING

    # ── Rule 3: coerce primitive ──────────────────────────────────────────
    prim = sig.get("primitive", "UNKNOWN")
    if prim == "BIAS":
        sig["primitive"] = "STABLE"
    elif prim in ("UNKNOWN", "", None):
        sig["primitive"] = "NONE"
    # TRADEOFF / DOMINANCE / REGIME_SHIFT are direction-agnostic — leave alone.

    # ── Rule 1: scrub motion words from summary ───────────────────────────
    summary = sig.get("summary", "") or ""
    lowered = summary.lower()
    if any(w in lowered for w in _MOTION_WORDS) or not summary:
        metric = sig.get("metric", "This metric")
        sig["summary"] = (
            f"{metric} is stable — no significant movement detected "
            f"relative to its historical baseline."
        )

    # ── Rule 4: split confidence (signal vs stability) ────────────────────
    raw_conf = float(sig.get("confidence", 0.0))
    # For FLAT, the engine's confidence actually expresses "confidence in
    # no-change", so route it to stability_confidence and dampen the
    # signal-level view.
    sig["stability_confidence"] = round(raw_conf, 4)
    sig["signal_confidence"]    = round(min(raw_conf, _FLAT_SIGNAL_SCORE_CEILING), 4)
    return sig


# ─────────────────────────────────────────────────────────────────────────────
# STATE COMPUTATION — strict logic, no fuzziness
# ─────────────────────────────────────────────────────────────────────────────

_VALID_STATES = {"ACTIONABLE", "NO_SIGNAL", "DATA_ISSUE", "MIXED"}


def _compute_state(
    *,
    quality_report: dict[str, Any],
    final_decisions: list[dict[str, Any]],
    data_quality_score: float,
    mapped_signals: list[dict[str, Any]] | None = None,
) -> str:
    """
    Resolve the output state using strict priority rules.

    Priority (hardened):
      1. BLOCKED quality                      → DATA_ISSUE (hard stop)
      2. Critical missingness / scaling flag  → DATA_ISSUE
      3. No decisions AND no strong signals   → NO_SIGNAL
      4. Low quality                          → DATA_ISSUE
      5. Conflicting signals (UP ⊕ DOWN)      → MIXED   (R1)
      6. Decisions + degraded quality         → MIXED
      7. Clean                                → ACTIONABLE
    """
    # Rule 1: quality gate blocks everything
    if quality_report.get("overall_status") == "BLOCKED":
        return "DATA_ISSUE"

    # Rule 2 (W3/W4): critical missingness or scaling forces DATA_ISSUE even
    # when the score itself hasn't dipped below 0.6.
    if quality_report.get("missing_critical"):
        return "DATA_ISSUE"
    if quality_report.get("scaling_suspects"):
        return "DATA_ISSUE"

    # Rule 3: no actionable decisions AND no meaningful signals
    signals = mapped_signals or []
    strong_signals = [
        s for s in signals
        if s.get("direction") in ("UP", "DOWN") and float(s.get("confidence", 0)) >= 0.5
    ]
    if len(final_decisions) == 0 and not strong_signals:
        return "NO_SIGNAL"

    # Rule 4: quality too low for reliable analysis
    if data_quality_score < 0.6:
        return "DATA_ISSUE"

    # Rule 5 (R1): conflicting directional signals → MIXED regardless of DQ
    ups   = {s.get("metric") for s in signals if s.get("direction") == "UP"}
    downs = {s.get("metric") for s in signals if s.get("direction") == "DOWN"}
    if ups and downs:
        return "MIXED"

    # Rule 6: decisions exist but quality is degraded
    if data_quality_score < 0.85:
        return "MIXED"

    # Rule 7: clean and actionable
    return "ACTIONABLE"


def _compute_state_reason(
    state: str,
    final_decisions: list[dict[str, Any]],
    data_quality_score: float,
    quality_report: dict[str, Any],
) -> dict[str, Any]:
    """Build structured state reason explaining why this state was assigned."""
    details: list[str] = []
    n_decisions = len(final_decisions)

    if state == "DATA_ISSUE":
        if quality_report.get("overall_status") == "BLOCKED":
            primary = "Data quality gate is BLOCKED"
            details.append("Quality report status: BLOCKED")
        else:
            primary = f"Data quality score ({data_quality_score:.0%}) is below minimum threshold"
            details.append(f"Quality score: {data_quality_score:.0%} (requires ≥60%)")
        if n_decisions > 0:
            details.append(f"{n_decisions} decision(s) found but suppressed due to quality")

    elif state == "NO_SIGNAL":
        primary = "No validated decisions produced by the pipeline"
        details.append(f"Quality score: {data_quality_score:.0%}")
        details.append("0 decisions passed validation")

    elif state == "MIXED":
        primary = f"{n_decisions} validated decision(s) with degraded data quality"
        details.append(f"Quality score: {data_quality_score:.0%} (below 85% threshold)")
        details.append(f"{n_decisions} decision(s) passed validation")

    else:  # ACTIONABLE
        primary = f"{n_decisions} validated decision(s) with clean data quality"
        details.append(f"Quality score: {data_quality_score:.0%}")
        details.append(f"{n_decisions} decision(s) passed validation")

    return {"primary": primary, "details": details}


# ─────────────────────────────────────────────────────────────────────────────
# HEADLINE GENERATION — deterministic, template-based
# ─────────────────────────────────────────────────────────────────────────────

def _compute_headline(
    state: str,
    final_decisions: list[dict[str, Any]],
    domain: str,
) -> str:
    """Generate a single-line headline from state and top decision."""
    if state == "DATA_ISSUE":
        return "Data quality prevents reliable analysis"

    if state == "NO_SIGNAL":
        return f"No structural changes detected in {domain} data"

    if state == "MIXED":
        top = final_decisions[0] if final_decisions else {}
        title = top.get("title", "Signals detected")
        return f"{title} — but data quality limits confidence"

    # ACTIONABLE
    if final_decisions:
        return final_decisions[0].get("title", "Actionable patterns detected")

    return "Analysis complete"


# ─────────────────────────────────────────────────────────────────────────────
# CONFIDENCE AGGREGATION — with state-based caps
# ─────────────────────────────────────────────────────────────────────────────

def _compute_confidence(
    final_decisions: list[dict[str, Any]],
    data_quality_score: float,
    state: str,
) -> float:
    """
    Aggregate confidence: weighted mean of top-N decisions,
    penalized by data quality score and capped by state.

    State-based adjustments:
      DATA_ISSUE → multiply by 0.5
      NO_SIGNAL  → cap at 0.6
    """
    if not final_decisions:
        return 0.0

    # Take top 3 decisions, weight by position
    weights = [1.0, 0.7, 0.5]
    total_w = 0.0
    total_c = 0.0

    for i, d in enumerate(final_decisions[:3]):
        w = weights[i] if i < len(weights) else 0.3
        c = float(d.get("confidence", 0.0))
        total_c += c * w
        total_w += w

    raw = total_c / total_w if total_w > 0 else 0.0

    # Penalize by data quality (quality < 1.0 reduces confidence)
    penalized = raw * min(data_quality_score, 1.0)

    # State-based caps — W7 hardened.
    # ACTIONABLE is capped at 0.92 because no statistical system should ever
    # claim certainty. Reserve the 0.92–1.0 band for calibrated uses only
    # (and we don't calibrate here yet).
    if state == "DATA_ISSUE":
        penalized *= 0.5
    elif state == "NO_SIGNAL":
        penalized = min(penalized, 0.6)
    elif state == "MIXED":
        penalized = min(penalized, 0.80)
    elif state == "ACTIONABLE":
        penalized = min(penalized, 0.92)

    return round(max(0.0, min(penalized, 1.0)), 4)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL MAPPING — with IDs, direction enum, capped at top 5
# ─────────────────────────────────────────────────────────────────────────────

def _map_signals(company_insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Map brain insights (validated signals) into canonical signal objects.
    Sorted by confidence descending, capped at top 5.
    """
    signals = []
    for s in company_insights:
        raw_dir = s.get("direction", s.get("subtype", "UNKNOWN"))
        metric = s.get("metric", "")
        mag    = round(float(s.get("magnitude_pct", 0.0)), 4)
        direction = _normalize_direction(raw_dir)
        primitive = s.get("primitive", "UNKNOWN")

        # R2 — human-readable default summary if upstream didn't provide one.
        # Format: "{metric} {direction-verb} by {magnitude}% vs baseline"
        provided = s.get("summary", "") or ""
        if not provided.strip():
            provided = _human_signal_summary(metric, direction, mag, primitive)

        sig = {
            "id":            "",  # placeholder, assigned after sort
            "metric":        metric,
            "direction":     direction,
            "magnitude_pct": mag,
            "confidence":    round(float(s.get("confidence", 0.0)), 4),
            "primitive":     primitive,
            "role":          s.get("role", "UNKNOWN"),
            "summary":       provided,
            "signal_score":  round(float(s.get("signal_score", 0.0)), 4),
        }
        # Semantic reconciliation pass — enforces FLAT invariants, adds
        # signal_confidence / stability_confidence split. Pure messaging
        # layer: does not touch confidence or detector math.
        sig = _reconcile_flat_signal(sig)
        signals.append(sig)

    # Sort by confidence descending, cap at 5
    signals.sort(key=lambda x: x["confidence"], reverse=True)
    signals = signals[:5]

    # Assign stable IDs after sort
    for i, sig in enumerate(signals):
        sig["id"] = f"signal_{i + 1}"

    return signals


# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY MAPPING
# ─────────────────────────────────────────────────────────────────────────────

def _map_data_quality(
    quality_report: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Map existing quality_report + profile into canonical data_quality block."""
    return {
        "score":             round(float(profile.get("data_quality_score", 0.0)), 4),
        "overall_status":    quality_report.get("overall_status", "UNKNOWN"),
        "forecast_mode":     quality_report.get("forecast_mode", "UNKNOWN"),
        "missing_columns":   quality_report.get("missing_pct", {}),
        "domain_violations": quality_report.get("domain_violations", {}),
        "warnings":          profile.get("warnings", []),
        "notes":             quality_report.get("notes", []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSION ANALYSIS MAPPING
# ─────────────────────────────────────────────────────────────────────────────

def _map_dimension_analysis(
    descriptive_insights: list[dict[str, Any]],
    segment_decisions: dict[str, list[dict[str, Any]]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Extract dimension analysis from descriptive profiler + segment engine."""
    dimensions = profile.get("dimensions", [])

    # Concentration risks from descriptive insights
    concentration_risks = []
    for di in descriptive_insights:
        if di.get("type") == "CONCENTRATION":
            ev = di.get("evidence", {})
            concentration_risks.append({
                "dimension":    di.get("dimension", ""),
                "metric":       di.get("metric", ""),
                "top_segment":  ev.get("top_segment", ""),
                "top_share":    round(float(ev.get("top_share", 0.0)), 4),
                "hhi":          round(float(ev.get("hhi", 0.0)), 4),
                "severity":     di.get("severity", "MEDIUM"),
            })

    # Variance drivers
    variance_drivers = []
    for di in descriptive_insights:
        if di.get("type") == "VARIANCE_DRIVER":
            ev = di.get("evidence", {})
            variance_drivers.append({
                "dimension":                di.get("dimension", ""),
                "metric":                   di.get("metric", ""),
                "explained_variance_ratio": round(float(ev.get("explained_variance_ratio", 0.0)), 4),
                "severity":                 di.get("severity", "MEDIUM"),
            })

    # Top segments from segment_decisions (significant only)
    top_segments = []
    for label, contexts in segment_decisions.items():
        if not isinstance(contexts, list):
            continue
        for ctx in contexts:
            if ctx.get("significant") and ctx.get("type") == "SEGMENT_CONTEXT":
                top_segments.append({
                    "dimension":     ctx.get("dimension", ""),
                    "segment":       ctx.get("segment_value", ""),
                    "metric":        ctx.get("metric", ""),
                    "deviation_pct": round(float(ctx.get("deviation", 0.0)) * 100, 2),
                    "direction":     ctx.get("global_direction", ""),
                })

    return {
        "dimensions":          dimensions,
        "segment_count":       sum(
            len([c for c in ctxs if isinstance(c, dict)])
            for ctxs in segment_decisions.values()
            if isinstance(ctxs, list)
        ),
        "concentration_risks": concentration_risks,
        "variance_drivers":    variance_drivers[:10],   # cap for readability
        "top_segments":        top_segments[:10],        # cap for readability
    }


# ─────────────────────────────────────────────────────────────────────────────
# DECISION MAPPING — with traces linking back to signals
# ─────────────────────────────────────────────────────────────────────────────

def _map_decisions(
    final_decisions: list[dict[str, Any]],
    mapped_signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Normalize compressed decisions into canonical shape.
    Each decision includes a trace linking it to the signals it was derived from.
    """
    # Build metric→signal_id lookup from mapped signals
    metric_to_signal_id: dict[str, str] = {}
    for sig in mapped_signals:
        m = sig.get("metric", "")
        if m:
            metric_to_signal_id[m] = sig["id"]

    mapped = []
    for i, d in enumerate(final_decisions):
        decision_id = f"decision_{i + 1}"

        # Resolve which signal IDs this decision was derived from
        raw_signals = d.get("signals", [])
        derived_from = []
        if isinstance(raw_signals, list):
            for s_metric in raw_signals:
                sid = metric_to_signal_id.get(s_metric, "")
                if sid:
                    derived_from.append(sid)

        # R3: concrete, auditable reasons for why this decision exists.
        why: list[str] = []
        conf_val = float(d.get("confidence", 0.0))
        prio     = d.get("priority", "MEDIUM")
        dtype    = d.get("type", "UNKNOWN")
        if derived_from:
            why.append(
                f"Derived from {len(derived_from)} validated signal(s): "
                f"{', '.join(derived_from)}"
            )
        if conf_val >= 0.70:
            why.append(f"Confidence ≥ 70% ({conf_val:.0%}) passed filter")
        elif conf_val >= 0.30:
            why.append(f"Confidence ≥ 30% ({conf_val:.0%}) — reportable tier")
        if prio == "HIGH":
            why.append("Priority=HIGH (top-decile impact or critical path)")
        if dtype and dtype != "UNKNOWN":
            why.append(f"Rule: {dtype} decision-type fired")
        if not why:
            why.append("Passed validation and de-duplication gates")

        mapped.append({
            "rank":              i + 1,
            "source":            d.get("source", "unknown"),
            "decision_type":     dtype,
            "title":             d.get("title", ""),
            "summary":           d.get("summary", ""),
            "action":            d.get("action", ""),
            "priority":          prio,
            "confidence":        round(conf_val, 4),
            "metric":            d.get("metric", ""),
            "signals":           raw_signals,
            "why_this_decision": why,
            "trace": {
                "decision_id":          decision_id,
                "derived_from_signals": derived_from,
            },
        })
    return mapped


# ─────────────────────────────────────────────────────────────────────────────
# ROOT CAUSE — structured from top decision + signals + segments
# ─────────────────────────────────────────────────────────────────────────────

def _compute_root_cause(
    final_decisions: list[dict[str, Any]],
    company_insights: list[dict[str, Any]],
    segment_decisions: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """
    Build a structured root_cause block from the top decision,
    its supporting signals, and affected segments.
    """
    if not final_decisions:
        return {
            "summary":              "No structural root cause identified",
            "primary_driver":       "",
            "contributing_signals": [],
            "affected_segments":    [],
        }

    top = final_decisions[0]
    top_signals = top.get("signals", [])

    # Find matching insights for the top decision's signals
    contributing = []
    for metric_name in (top_signals[:3] if isinstance(top_signals, list) else []):
        for ins in company_insights:
            if ins.get("metric") == metric_name:
                contributing.append({
                    "metric":    metric_name,
                    "direction": _normalize_direction(
                        ins.get("direction", ins.get("subtype", ""))
                    ),
                    "primitive": ins.get("primitive", ""),
                    "confidence": round(float(ins.get("confidence", 0.0)), 4),
                })
                break

    # Extract affected segments from segment_decisions
    affected_segments = []
    for label, contexts in segment_decisions.items():
        if not isinstance(contexts, list):
            continue
        for ctx in contexts:
            if ctx.get("significant") and ctx.get("type") == "SEGMENT_CONTEXT":
                affected_segments.append({
                    "dimension": ctx.get("dimension", ""),
                    "segment":   ctx.get("segment_value", ""),
                    "metric":    ctx.get("metric", ""),
                    "deviation": round(float(ctx.get("deviation", 0.0)) * 100, 2),
                })
    # Cap to top 5 most significant
    affected_segments.sort(key=lambda x: abs(x.get("deviation", 0)), reverse=True)
    affected_segments = affected_segments[:5]

    # W11 hardened — only claim a root cause when we have real corroborating
    # evidence. ≥2 contributing signals OR ≥1 affected segment → "cause".
    # Otherwise report UNKNOWN rather than re-using the decision text.
    has_real_cause = len(contributing) >= 2 or len(affected_segments) >= 1
    driver = top.get("metric", "")

    if has_real_cause:
        rc_summary = top.get("summary") or top.get("title") or ""
        rc_status  = "RESOLVED"
    else:
        rc_summary = (
            f"Root cause is UNKNOWN. The top signal is on {driver or 'the primary metric'}, "
            f"but there is no corroborating cross-metric or segment evidence to "
            f"attribute it causally. Treat as a single-signal alert."
        ) if driver else (
            "Root cause is UNKNOWN. No corroborating evidence across metrics "
            "or segments."
        )
        rc_status = "UNKNOWN"

    return {
        "summary":              rc_summary,
        "status":               rc_status,
        "primary_driver":       driver,
        "contributing_signals": contributing,
        "affected_segments":    affected_segments,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EXPLAINABILITY — why this decision + supporting signals
# ─────────────────────────────────────────────────────────────────────────────

def _compute_explainability(
    final_decisions: list[dict[str, Any]],
    aegis_insights: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build explainability block from aegis insights (typed patterns)
    and final compressed decisions.
    """
    # Extract typed insight summaries
    insight_explanations = []
    for ins in aegis_insights[:5]:
        insight_explanations.append({
            "type":       ins.get("type", "UNKNOWN"),
            "title":      ins.get("title", ""),
            "confidence": round(float(ins.get("confidence", 0.0)), 4),
            "fact":       ins.get("fact", ""),
        })

    # Top decision's why
    decision_reasons = []
    for d in final_decisions[:3]:
        title = d.get("title", "")
        summary = d.get("summary", "")
        if title or summary:
            decision_reasons.append(title or summary)

    return {
        "why_this_decision":  decision_reasons,
        "supporting_signals": insight_explanations,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ASSUMPTIONS + LIMITATIONS
# ─────────────────────────────────────────────────────────────────────────────

def _compute_assumptions(
    profile: dict[str, Any],
    metadata: dict[str, Any],
    state: str,
) -> list[str]:
    """
    List assumptions that constrain the analysis.
    Derived from profile and metadata — not invented.
    """
    assumptions = []

    if not profile.get("ordered_data"):
        assumptions.append(
            "No temporal column detected — signals reflect row order, not time order"
        )

    if not profile.get("time_column") and profile.get("year_column"):
        assumptions.append(
            "Temporal structure derived from composite YEAR/MONTH columns"
        )

    maturity = metadata.get("baseline_maturity", "")
    if maturity == "IMMATURE":
        assumptions.append(
            "Baseline is immature (first upload) — confidence is penalized"
        )
    elif maturity == "DEVELOPING":
        assumptions.append(
            "Baseline is developing (fewer than 5 uploads) — confidence may improve with more data"
        )

    if state == "MIXED":
        assumptions.append(
            "Data quality is degraded — decisions are present but should be verified"
        )

    if not profile.get("dimensions"):
        assumptions.append(
            "No categorical dimensions detected — segment analysis was skipped"
        )

    return assumptions


def _compute_limitations(profile: dict[str, Any]) -> list[str]:
    """
    Static + context-derived limitations.
    These are inherent boundaries of the analysis, not failures.
    """
    limitations = [
        "No external factors considered (macroeconomic, competitive, seasonal)",
        "Single dataset analysis — no cross-dataset correlation",
        "Causal relationships are inferred, not experimentally validated",
    ]

    if not profile.get("dimensions"):
        limitations.append("No segment-level analysis available (no dimensions detected)")

    if not profile.get("ordered_data"):
        limitations.append("Temporal trend analysis limited (no time-ordered data)")

    return limitations


# ─────────────────────────────────────────────────────────────────────────────
# ACTION — top-level action string from decisions
# ─────────────────────────────────────────────────────────────────────────────

def _compute_action(
    state: str,
    final_decisions: list[dict[str, Any]],
) -> str:
    """Top-level action derived from state and top decision."""
    if state == "DATA_ISSUE":
        return "Resolve data quality issues before acting on signals"

    if state == "NO_SIGNAL":
        return "No action required — system is operating within expected parameters"

    if state == "MIXED":
        top_action = ""
        if final_decisions:
            top_action = final_decisions[0].get("action", "")
        return top_action or "Review signals with caution — data quality is degraded"

    # ACTIONABLE
    if final_decisions:
        return final_decisions[0].get("action", "Investigate the top structural pattern")

    return "No specific action identified"


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def compose_structured_output(
    *,
    system_state: str,
    profile: dict[str, Any],
    quality_report: dict[str, Any],
    final_decisions: list[dict[str, Any]],
    global_decisions: list[dict[str, Any]],
    company_insights: list[dict[str, Any]],
    aegis_insights: list[dict[str, Any]],
    relative_decisions: list[dict[str, Any]],
    segment_decisions: dict[str, list[dict[str, Any]]],
    descriptive_insights: list[dict[str, Any]],
    decision_meta: dict[str, Any],
    reality_snapshot: dict[str, Any],
    drift_report: dict[str, Any] | None,
    metadata: dict[str, Any],
    tenant_id: str,
    domain: str,
    data_mode: str,
) -> dict[str, Any]:
    """
    Assemble the canonical AEGIS structured output from existing pipeline outputs.

    This is a PURE TRANSFORMATION — no business logic, no data access.
    Every value is derived from an already-computed pipeline artifact.

    Returns:
        Canonical schema v1.0.0 with: meta, state, state_reason, headline,
        confidence, signals, data_quality, dimension_analysis, decisions,
        root_cause, explainability, action, assumptions, limitations
    """
    data_quality_score = float(profile.get("data_quality_score", 0.0))

    # ── Signals (mapped first — needed for conflict-aware state) ──────────
    mapped_signals = _map_signals(company_insights)

    # ── State (conflict-aware, W3/W4/R1 hardened) ─────────────────────────
    state = _compute_state(
        quality_report=quality_report,
        final_decisions=final_decisions,
        data_quality_score=data_quality_score,
        mapped_signals=mapped_signals,
    )

    # ── State reason ──────────────────────────────────────────────────────
    state_reason = _compute_state_reason(
        state, final_decisions, data_quality_score, quality_report,
    )

    # ── Headline ──────────────────────────────────────────────────────────
    headline = _compute_headline(state, final_decisions, domain)

    # ── Confidence (state-aware caps) ─────────────────────────────────────
    confidence = _compute_confidence(final_decisions, data_quality_score, state)

    # ── Decisions (with traces linking to signal IDs) ─────────────────────
    mapped_decisions = _map_decisions(final_decisions, mapped_signals)

    # ── Assemble ──────────────────────────────────────────────────────────
    return {
        "meta": {
            "response_id":         str(uuid.uuid4()),
            "schema_version":      SCHEMA_VERSION,
            "aegis_version":       _aegis_version,
            "tenant":              tenant_id,
            "domain":              domain,
            "data_mode":           data_mode,
            "row_count":           profile.get("row_count", 0),
            "metrics_analyzed":    profile.get("valid_metrics", []),
            "dimensions_detected": profile.get("dimensions", []),
            "ordered_data":        profile.get("ordered_data", False),
            "processing_time_sec": metadata.get("processing_time_sec", 0.0),
            "baseline_maturity":   metadata.get("baseline_maturity", "UNKNOWN"),
            "upload_count":        metadata.get("upload_count", 0),
            "pipeline_counts": {
                "input_signals":             decision_meta.get("input_signals", 0),
                "normalized_events":         decision_meta.get("normalized_events", 0),
                "decisions_generated":       decision_meta.get("decisions_generated", 0),
                "decisions_after_validation": decision_meta.get("decisions_after_validation", 0),
            },
        },

        "state":        state,
        "state_reason": state_reason,
        "headline":     headline,
        "confidence":   confidence,

        "signals":            mapped_signals,
        "data_quality":       _map_data_quality(quality_report, profile),
        "dimension_analysis": _map_dimension_analysis(
            descriptive_insights, segment_decisions, profile,
        ),
        "decisions":      mapped_decisions,
        "root_cause":     _compute_root_cause(
            final_decisions, company_insights, segment_decisions,
        ),
        "explainability": _compute_explainability(final_decisions, aegis_insights),
        "action":         _compute_action(state, final_decisions),
        "assumptions":    _compute_assumptions(profile, metadata, state),
        "limitations":    _compute_limitations(profile),
    }
