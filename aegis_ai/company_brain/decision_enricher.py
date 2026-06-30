"""
aegis_ai/company_brain/decision_enricher.py
============================================
Domain-Agnostic Decision Enrichment Layer

Injects structured epistemic context into every synthesized decision:
  - FACT     : pure observation (what is happening)
  - PATTERN  : universal relationship between metrics (no domain assumptions)
  - IMPACT   : what dimensions of the business could be affected
  - ACTION   : what to investigate or do
  - HYPOTHESIS: multiple possible explanations, framed as possibilities

Design principles
-----------------
* NEVER names a domain (marketing, finance, supply chain, etc.)
* NEVER uses specific metric names in logic — only structural roles
* NEVER assigns a single fixed cause
* ALL analysis is derived from: direction, magnitude, role, confidence,
  segment_context, supporting_metrics, conflicting_metrics
* Deterministic: same inputs → same outputs
* Fail-open: enrichment errors never mutate or remove decisions

Universal metric roles recognised (from event_engine)
------------------------------------------------------
  INPUT    — resources going IN  (cost, spend, effort, volume injected)
  OUTPUT   — results coming OUT  (throughput, transactions, interactions)
  VALUE    — monetised / scored outcomes (revenue, profit, score)
  QUALITY  — defect / risk / error metrics (lower-is-better convention)
  COST     — explicit cost / expense signals
  TRANSFER — inventory / stock / pipeline flow metrics
  UNKNOWN  — not yet classified

Structural patterns (direction-based, role-agnostic)
----------------------------------------------------
  INPUT↑  + OUTPUT↓        → FUNNEL_INEFFICIENCY
  INPUT↓  + OUTPUT↑/VALUE↑ → EFFICIENCY_GAIN
  INPUT↑  + OUTPUT↑/VALUE↑ → GROWTH_MOMENTUM
  INPUT↓  + OUTPUT↓/VALUE↓ → DEMAND_CONTRACTION
  VALUE↑  + COST↑          → MARGIN_PRESSURE
  VALUE↓  + COST↑          → DOUBLE_SQUEEZE
  QUALITY↑ (rising defect) → QUALITY_RISK
  TRANSFER shifting         → FLOW_DISRUPTION
  All ↑ same direction      → BROAD_EXPANSION
  All ↓ same direction      → BROAD_CONTRACTION
  Mixed directions          → DIVERGENCE
"""

from __future__ import annotations

from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# DIRECTIONALITY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _is_up(e: dict) -> bool:
    return e.get("direction") == "UPWARD"


def _is_down(e: dict) -> bool:
    return e.get("direction") == "DOWNWARD"


def _verb(direction: str) -> str:
    return {
        "UPWARD":   "increasing",
        "DOWNWARD": "decreasing",
    }.get(direction, "shifting")


def _metric_names(events: list[dict]) -> list[str]:
    return sorted(set(e.get("metric", "") for e in events if e.get("metric")))


def _avg_magnitude(events: list[dict]) -> float:
    vals = [abs(e.get("magnitude_pct", 0.0)) for e in events]
    return round(sum(vals) / len(vals), 4) if vals else 0.0


def _fmt_list(items: list[str]) -> str:
    if not items:
        return "affected metrics"
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURAL PATTERN DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

_PatternResult = tuple[str, str]   # (pattern_id, pattern_description)


def _detect_structural_pattern(
    groups: dict[str, list[dict]],
    signals: list[dict],
) -> _PatternResult:
    """
    Identify the universal structural pattern present in the signal set.
    Uses only directional roles — zero domain-specific logic.
    """
    inp   = groups.get("INPUT", [])
    out   = groups.get("OUTPUT", [])
    val   = groups.get("VALUE", [])
    qual  = groups.get("QUALITY", [])
    cost  = groups.get("COST", [])
    trans = groups.get("TRANSFER", [])

    inp_up   = [e for e in inp   if _is_up(e)]
    inp_down = [e for e in inp   if _is_down(e)]
    out_up   = [e for e in out   if _is_up(e)]
    out_down = [e for e in out   if _is_down(e)]
    val_up   = [e for e in val   if _is_up(e)]
    val_down = [e for e in val   if _is_down(e)]
    qual_up  = [e for e in qual  if _is_up(e)]
    cost_up  = [e for e in cost  if _is_up(e)]

    # INPUT↑ while OUTPUT/VALUE↓ — funnel or conversion inefficiency
    if inp_up and (out_down or val_down):
        return (
            "FUNNEL_INEFFICIENCY",
            "input metrics are increasing while output or value metrics are declining — "
            "indicating potential loss of conversion efficiency between input and output layers",
        )

    # INPUT↓ while OUTPUT↑ or VALUE↑ — efficiency gain
    if inp_down and (out_up or val_up):
        return (
            "EFFICIENCY_GAIN",
            "input metrics are declining while output or value metrics are rising — "
            "indicating potential improvement in operational efficiency or unit economics",
        )

    # INPUT↑ + OUTPUT↑/VALUE↑ — growth momentum
    if inp_up and (out_up or val_up):
        return (
            "GROWTH_MOMENTUM",
            "input and output metrics are both increasing in the same direction — "
            "indicating potential broad-based growth or capacity expansion",
        )

    # INPUT↓ + OUTPUT↓/VALUE↓ — demand contraction
    if inp_down and (out_down or val_down):
        return (
            "DEMAND_CONTRACTION",
            "input and output metrics are both declining — "
            "indicating potential systemic demand reduction or resource withdrawal",
        )

    # VALUE↑ + COST↑ — margin pressure
    if val_up and cost_up:
        return (
            "MARGIN_PRESSURE",
            "value metrics and cost metrics are both rising — "
            "indicating potential margin compression where revenue gains may be offset by rising costs",
        )

    # VALUE↓ + COST↑ — double squeeze
    if val_down and cost_up:
        return (
            "DOUBLE_SQUEEZE",
            "value metrics are declining while cost metrics are rising — "
            "indicating potential structural deterioration of unit economics from both directions",
        )

    # QUALITY risk (lower-is-better metrics rising)
    if qual_up:
        return (
            "QUALITY_RISK",
            "quality or risk metrics are worsening — "
            "indicating potential deterioration in output quality, defect rates, or operational reliability",
        )

    # TRANSFER movement
    if trans:
        dirs = {e.get("direction") for e in trans}
        if len(dirs) == 1:
            d = next(iter(dirs))
            return (
                "FLOW_SHIFT",
                f"pipeline or transfer metrics are uniformly {_verb(d)} — "
                "indicating potential change in throughflow, inventory balance, or capacity utilisation",
            )
        return (
            "FLOW_DISRUPTION",
            "pipeline or transfer metrics are moving in mixed directions — "
            "indicating potential disruption in flow balance or sequencing",
        )

    # All signals same direction
    all_dirs = {e.get("direction") for e in signals if e.get("direction") in ("UPWARD", "DOWNWARD")}
    if len(all_dirs) == 1:
        d = next(iter(all_dirs))
        if d == "UPWARD":
            return (
                "BROAD_EXPANSION",
                "all monitored metrics are increasing simultaneously — "
                "indicating potential broad-based expansion or data-level shift",
            )
        return (
            "BROAD_CONTRACTION",
            "all monitored metrics are declining simultaneously — "
            "indicating potential broad-based contraction or structural withdrawal",
        )

    # Mixed / diverging
    return (
        "DIVERGENCE",
        "metrics are moving in opposing directions — "
        "indicating potential structural divergence between different layers of the system",
    )


# ─────────────────────────────────────────────────────────────────────────────
# FACT BLOCK
# ─────────────────────────────────────────────────────────────────────────────

def _build_fact(decision: dict, signals: list[dict]) -> str:
    """Pure observation — what is numerically happening. No interpretation."""
    d_type    = decision.get("type", "UNKNOWN")
    metrics   = decision.get("signals", [])
    conf      = decision.get("confidence", 0.0)
    impact    = decision.get("impact", 0.0)
    priority  = decision.get("priority", "LOW")
    mag       = _avg_magnitude(signals) if signals else 0.0

    metric_str = _fmt_list(metrics[:3])
    mag_pct    = round(mag * 100, 1)
    conf_pct   = round(conf * 100, 1)

    seg_phrase = ""
    segs = decision.get("segments", [])
    if segs:
        top = segs[0]
        dev_pct = round(abs(top.get("deviation", 0.0)) * 100)
        seg_phrase = (
            f" The strongest localised signal appears in {top.get('value', '')} "
            f"({top.get('dimension', '')}), showing {dev_pct}% deviation from the global average."
        )

    return (
        f"Pattern type [{d_type}] detected across {metric_str}. "
        f"Average magnitude of change is {mag_pct}%, with a signal confidence of {conf_pct}%. "
        f"Priority assessed as {priority}."
        + seg_phrase
    )


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN BLOCK
# ─────────────────────────────────────────────────────────────────────────────

def _build_pattern(
    decision: dict,
    groups: dict[str, list[dict]],
    signals: list[dict],
    pattern_id: str,
    pattern_desc: str,
) -> str:
    """Describes the structural relationship between metric roles — no domain naming."""
    supporting = decision.get("supporting_metrics", [])
    conflicting = decision.get("conflicting_metrics", [])

    validation_clause = ""
    if supporting and conflicting:
        validation_clause = (
            f" Cross-metric validation shows {_fmt_list(supporting[:2])} "
            f"supporting this pattern while {_fmt_list(conflicting[:2])} "
            f"are moving in the opposite direction, this may suggest internal tension within the system."
        )
    elif supporting:
        validation_clause = (
            f" Cross-metric validation shows {_fmt_list(supporting[:2])} "
            f"independently corroborating this pattern, increasing signal reliability."
        )
    elif conflicting:
        validation_clause = (
            f" Cross-metric validation flags {_fmt_list(conflicting[:2])} "
            f"as moving counter to this pattern, this may suggest noise or partial recovery."
        )

    return (
        f"Structural pattern [{pattern_id}] identified: {pattern_desc}."
        + validation_clause
    )


# ─────────────────────────────────────────────────────────────────────────────
# IMPACT BLOCK
# ─────────────────────────────────────────────────────────────────────────────

_PATTERN_IMPACT_MAP: dict[str, str] = {
    "FUNNEL_INEFFICIENCY": (
        "This pattern has potential implications for cost efficiency, output throughput, "
        "and overall value delivery. Resources consumed by inputs are not translating proportionally "
        "into outputs, indicating potential waste or leakage somewhere between input and output layers."
    ),
    "EFFICIENCY_GAIN": (
        "This pattern has potential positive implications for unit economics and operational margin. "
        "Less input is producing more output, which may indicate structural productivity improvement "
        "or favourable volume-cost dynamics."
    ),
    "GROWTH_MOMENTUM": (
        "This pattern has potential implications for capacity, resource planning, and output scalability. "
        "Broad simultaneous metric growth may place stress on throughput limits or require proportional "
        "scaling of inputs to sustain output quality."
    ),
    "DEMAND_CONTRACTION": (
        "This pattern has potential implications for revenue, throughput, and resource utilisation. "
        "Simultaneous declines across input and output layers suggest a systemic reduction in demand "
        "or supply availability that may compound over time."
    ),
    "MARGIN_PRESSURE": (
        "This pattern has potential implications for profitability and operational sustainability. "
        "Rising costs alongside rising value metrics may indicate that efficiency gains are not keeping "
        "pace with cost growth, increasing risk of margin erosion."
    ),
    "DOUBLE_SQUEEZE": (
        "This pattern has potential critical implications for financial health and operational viability. "
        "Simultaneous deterioration in value output and cost input creates compounding pressure on unit "
        "economics that, if sustained, may become structurally destabilising."
    ),
    "QUALITY_RISK": (
        "This pattern has potential implications for operational reliability, customer or stakeholder "
        "experience, and downstream output quality. Worsening quality metrics often precede larger "
        "systemic failures if left unaddressed."
    ),
    "FLOW_SHIFT": (
        "This pattern has potential implications for pipeline balance, utilisation, and downstream "
        "capacity. A uniform directional shift in flow metrics may signal changing throughput rates "
        "or inventory dynamics."
    ),
    "FLOW_DISRUPTION": (
        "This pattern has potential implications for sequencing, pipeline reliability, and capacity "
        "allocation. Mixed directional movements in flow metrics may indicate a disruption to normal "
        "operational sequencing."
    ),
    "BROAD_EXPANSION": (
        "This pattern has potential implications for resource capacity, throughput limits, and "
        "sustainability of growth. Broad simultaneous expansion requires monitoring to distinguish "
        "genuine growth from measurement or data artefacts."
    ),
    "BROAD_CONTRACTION": (
        "This pattern has potential implications for revenue, throughput, and organisational capacity. "
        "Broad simultaneous decline increases systemic risk and reduces the organisation's margin "
        "for response and recovery."
    ),
    "DIVERGENCE": (
        "This pattern has potential implications for signal reliability and strategic alignment. "
        "Diverging metrics may indicate structural imbalance, mixed recovery, or conflicting "
        "pressures operating on different parts of the system simultaneously."
    ),
}

_DEFAULT_IMPACT = (
    "This pattern has potential implications for operational efficiency, cost, and output quality. "
    "The specific dimensions of impact depend on the relationship between the changing metrics "
    "and their role in the broader system."
)


def _build_impact(pattern_id: str, decision: dict) -> str:
    base = _PATTERN_IMPACT_MAP.get(pattern_id, _DEFAULT_IMPACT)

    segs = decision.get("segments", [])
    if segs:
        top = segs[0]
        dev_pct = round(abs(top.get("deviation", 0.0)) * 100)
        concentration = (
            f" Concentration risk is elevated: {top.get('value', '')} "
            f"({top.get('dimension', '')}) shows {dev_pct}% deviation, "
            f"indicating potential localised exposure that may not be visible at the aggregate level."
        )
        base += concentration

    return base


# ─────────────────────────────────────────────────────────────────────────────
# ACTION BLOCK
# ─────────────────────────────────────────────────────────────────────────────

_PATTERN_ACTION_MAP: dict[str, list[str]] = {
    "FUNNEL_INEFFICIENCY": [
        "Identify the specific stage between input injection and output realisation where drop-off is occurring.",
        "Compare input-to-output ratios across segments to determine whether the inefficiency is localised or broad.",
        "Evaluate whether input quality, composition, or timing has changed alongside the quantity increase.",
    ],
    "EFFICIENCY_GAIN": [
        "Identify which operational or structural change is driving the improvement and validate its sustainability.",
        "Determine whether the gain is uniform across segments or concentrated in specific subgroups.",
        "Assess whether input reductions are intentional or reflect constraint — both can produce this pattern.",
    ],
    "GROWTH_MOMENTUM": [
        "Investigate which input or enabling factor is the primary driver of simultaneous metric growth.",
        "Assess capacity constraints — determine if current infrastructure can sustain the growth trajectory.",
        "Monitor for reversal signals: rapid growth phases can precede sharp corrections.",
    ],
    "DEMAND_CONTRACTION": [
        "Determine whether the contraction is market-wide, segment-specific, or concentrated in particular inputs.",
        "Review whether the decline is accelerating or stabilising — plateau versus freefall require different responses.",
        "Investigate whether any external condition change correlates with the onset of the decline.",
    ],
    "MARGIN_PRESSURE": [
        "Analyse whether cost growth is proportional to output growth or outpacing it.",
        "Identify the specific cost components driving the increase and assess whether they are variable or fixed.",
        "Evaluate pricing or output mix for opportunities to restore margin without reducing volume.",
    ],
    "DOUBLE_SQUEEZE": [
        "Treat this as a high-priority investigation — simultaneous value decline and cost increase is structurally unsustainable.",
        "Isolate whether value decline and cost increase share a common root cause or are independent pressures.",
        "Assess headroom available before systemic thresholds are breached.",
    ],
    "QUALITY_RISK": [
        "Identify which process, segment, or input is most closely associated with the quality metric deterioration.",
        "Determine whether quality metrics are leading indicators of a larger breakdown or isolated incidents.",
        "Evaluate whether output volume changes are masking the quality signal.",
    ],
    "FLOW_SHIFT": [
        "Investigate whether the directional shift is driven by upstream supply changes or downstream demand changes.",
        "Monitor for capacity saturation or depletion effects that may follow the current directional shift.",
        "Determine whether the shift is controlled and expected or an unplanned deviation.",
    ],
    "FLOW_DISRUPTION": [
        "Identify where in the pipeline sequence the directional divergence originates.",
        "Assess whether disruption is caused by input variability, processing constraints, or output demand mismatch.",
        "Prioritise stabilisation of the metric with the highest magnitude change.",
    ],
    "BROAD_EXPANSION": [
        "Validate that the broad expansion reflects genuine operational growth before scaling resources.",
        "Identify the leading metric — which dimension is expanding first and pulling others up.",
        "Monitor for early signs of over-extension or resource bottlenecks.",
    ],
    "BROAD_CONTRACTION": [
        "Determine whether the contraction is driven by a single systemic event or multiple independent pressures.",
        "Prioritise triage of the highest-impact metrics first while monitoring for secondary effects.",
        "Assess whether any metrics are resisting the contraction — these may represent resilience anchors.",
    ],
    "DIVERGENCE": [
        "Investigate the structural relationship between the metrics moving in opposite directions.",
        "Determine whether divergence reflects a genuine structural shift or measurement or timing artefacts.",
        "Segment the data to identify whether the divergence is global or localised to specific subgroups.",
    ],
}

_DEFAULT_ACTIONS = [
    "Segment the data to determine whether the pattern is localised or broad-based.",
    "Cross-reference the changing metrics against historical baselines to assess novelty.",
    "Identify which metric is the leading indicator and which are lagging followers.",
]


def _build_action(pattern_id: str, decision: dict) -> list[str]:
    actions = list(_PATTERN_ACTION_MAP.get(pattern_id, _DEFAULT_ACTIONS))

    # Append segment-specific investigation if segment deviation is significant
    segs = decision.get("segments", [])
    if segs:
        top = segs[0]
        dev_pct = round(abs(top.get("deviation", 0.0)) * 100)
        if dev_pct >= 30:
            actions.append(
                f"Prioritise investigation within {top.get('value', '')} "
                f"({top.get('dimension', '')}) — this segment shows {dev_pct}% deviation "
                f"from the global average and is the most likely concentration point."
            )

    return actions[:4]


# ─────────────────────────────────────────────────────────────────────────────
# HYPOTHESIS BLOCK
# ─────────────────────────────────────────────────────────────────────────────

_PATTERN_HYPOTHESES: dict[str, list[str]] = {
    "FUNNEL_INEFFICIENCY": [
        "Possible cause: the composition or quality of inputs may have changed, reducing their effectiveness at generating outputs.",
        "Possible cause: a bottleneck may have emerged at a downstream processing stage, capping output regardless of input volume.",
        "Possible cause: the relationship between inputs and outputs may have a lag structure — outputs may recover in subsequent periods.",
        "This may suggest: an upstream volumetric strategy is operating without corresponding downstream optimisation.",
    ],
    "EFFICIENCY_GAIN": [
        "This may suggest: a structural improvement in conversion rates, processing logic, or resource allocation has occurred.",
        "Possible cause: lower-performing input categories may have been removed, improving the overall input-to-output ratio.",
        "Possible cause: output growth may be driven by lag effects from prior-period inputs rather than current-period efficiency.",
        "This may suggest: the system has reached a more balanced operating point — sustainability should be validated.",
    ],
    "GROWTH_MOMENTUM": [
        "Possible cause: an enabling condition — capacity expansion, a favourable external factor, or a process improvement — may be driving coordinated growth.",
        "This may suggest: compound growth dynamics where early metric gains are enabling secondary gains across the system.",
        "Possible cause: the measurement window may coincide with a cyclical peak rather than a structural trend.",
        "This may suggest: a successful structural change has entered a self-reinforcing phase.",
    ],
    "DEMAND_CONTRACTION": [
        "Possible cause: an external condition affecting demand may be reducing both the willingness to input and the ability to generate output.",
        "Possible cause: a key enabling component of the system may have been reduced, withdrawing supply from multiple metric layers simultaneously.",
        "This may suggest: a cyclical trough in a recurring demand pattern rather than a structural decline.",
        "Possible cause: competitive or substitution dynamics may be redirecting demand away from the current system.",
    ],
    "MARGIN_PRESSURE": [
        "Possible cause: cost inputs are scaling faster than the value outputs they generate, indicating potential economies-of-scale breakdown.",
        "This may suggest: the value metric growth is driven by volume rather than price, which dilutes per-unit margin.",
        "Possible cause: a fixed cost base is being spread across fewer high-margin activities, increasing cost concentration.",
        "This may suggest: rising input costs are being partially absorbed, temporarily hiding the full margin impact.",
    ],
    "DOUBLE_SQUEEZE": [
        "Possible cause: an external shock may be simultaneously reducing output value and increasing operational costs.",
        "This may suggest: the system is operating in a structural inefficiency zone where neither cost nor value levers are functioning normally.",
        "Possible cause: value metrics may be lagging a prior cost increase, with recovery not yet visible in the current measurement window.",
        "This may suggest: a compounding feedback loop where declining value reduces capacity to invest in cost reduction.",
    ],
    "QUALITY_RISK": [
        "Possible cause: an upstream input quality degradation may be propagating into output quality metrics.",
        "Possible cause: increased throughput volume may be exceeding quality-control capacity, causing quality drift at scale.",
        "This may suggest: a process or tooling change introduced in a prior period is manifesting quality effects in the current window.",
        "Possible cause: the metric itself may be a composite indicator where one constituent component is deteriorating while others remain stable.",
    ],
    "FLOW_SHIFT": [
        "This may suggest: upstream supply dynamics have changed, pushing more or less volume through the pipeline.",
        "Possible cause: downstream demand changes have altered the pull signal, causing reactive flow adjustment.",
        "Possible cause: the shift may reflect a controlled rebalancing rather than an unplanned perturbation.",
        "This may suggest: seasonal or cyclical throughput patterns are manifesting in the current window.",
    ],
    "FLOW_DISRUPTION": [
        "Possible cause: different pipeline stages may be responding to different time-lagged signals, creating directional divergence.",
        "This may suggest: a redistribution event is occurring — some flow paths are being favoured at the expense of others.",
        "Possible cause: external constraints on specific flow paths may be redirecting volume toward unconstrained alternatives.",
        "This may suggest: the measurement window captures a transition state rather than a stable operating pattern.",
    ],
    "BROAD_EXPANSION": [
        "Possible cause: a favourable enabling condition is lifting multiple metrics simultaneously.",
        "This may suggest: a data artefact — a measurement expansion, scope change, or period redefinition — rather than genuine operational growth.",
        "Possible cause: prior-period underperformance created a low-base effect that is making current growth appear disproportionate.",
        "This may suggest: genuine compounding growth where early gains are creating positive feedback across the system.",
    ],
    "BROAD_CONTRACTION": [
        "Possible cause: a single systemic constraint or disruption may be propagating effects across multiple metric layers.",
        "This may suggest: a seasonal or cyclical contraction that recurs in this measurement window.",
        "Possible cause: a data or measurement issue — scope reduction, exclusion of records — rather than genuine operational decline.",
        "This may suggest: a coordinated withdrawal or reallocation decision that is compressing multiple metrics simultaneously.",
    ],
    "DIVERGENCE": [
        "This may suggest: one metric is leading and the other is lagging — the divergence may resolve once the lag dissipates.",
        "Possible cause: the two metrics may be responding to different causal drivers that happen to be moving simultaneously.",
        "This may suggest: a structural decoupling between formerly correlated system layers.",
        "Possible cause: segment-level mixing effects may be creating divergence at the aggregate level that does not exist at the segment level.",
    ],
}

_DEFAULT_HYPOTHESES = [
    "Possible cause: an external condition not captured in the current dataset may be influencing the observed pattern.",
    "This may suggest: a lag between causal event and measurable effect is creating pattern distortion across the time window.",
    "Possible cause: segment-level dynamics may be driving aggregate results in a direction that misrepresents local behaviour.",
    "This may suggest: a measurement or data ingestion change may be contributing to the apparent pattern.",
]


def _build_hypothesis(pattern_id: str, decision: dict, signals: list[dict]) -> list[str]:
    hypotheses = list(_PATTERN_HYPOTHESES.get(pattern_id, _DEFAULT_HYPOTHESES))

    # Add concentration hypothesis if strong segment deviation
    segs = decision.get("segments", [])
    if segs:
        top = segs[0]
        dev_pct = round(abs(top.get("deviation", 0.0)) * 100)
        if dev_pct >= 40:
            hypotheses.insert(0,
                f"Indicating potential concentration effect: {top.get('value', '')} "
                f"({top.get('dimension', '')}) shows {dev_pct}% deviation, "
                f"which may be disproportionately driving the aggregate pattern — "
                f"possible causes include localised operational differences or selective reporting."
            )

    # Add conflict-based hypothesis if cross-validation flagged conflicts
    conflicting = decision.get("conflicting_metrics", [])
    if conflicting:
        hypotheses.append(
            f"This may suggest: {_fmt_list(conflicting[:2])} moving in opposition "
            f"could indicate partial recovery, measurement timing differences, "
            f"or a system where different metric layers are under different pressures simultaneously."
        )

    return hypotheses[:5]


# ─────────────────────────────────────────────────────────────────────────────
# GROUPS RECONSTRUCTION FROM DECISION SIGNALS + SOURCE EVENTS
# ─────────────────────────────────────────────────────────────────────────────

def _build_groups(signals: list[dict]) -> dict[str, list[dict]]:
    """Group validated events by their role — mirrors synthesize_decisions grouping."""
    groups: dict[str, list] = {
        r: [] for r in ("INPUT", "OUTPUT", "VALUE", "COST", "QUALITY", "TRANSFER", "UNKNOWN")
    }
    for e in signals:
        role = e.get("role", "UNKNOWN")
        if role not in groups:
            role = "UNKNOWN"
        groups[role].append(e)
    return groups


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def enrich_decisions(
    decisions: list[dict[str, Any]],
    validated_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Inject domain-agnostic epistemic enrichment into every decision.

    Each decision receives an ``enrichment`` block containing:
        fact       — pure structural observation
        pattern    — universal relationship description
        impact     — potential business dimensions affected
        action     — list of investigation / response steps
        hypothesis — list of possible explanations (possibilities, not conclusions)

    Args:
        decisions:        decisions from synthesize_decisions() / cross_validate_decisions()
        validated_events: events from event_engine.normalize_events()
                          (used to reconstruct role groups for pattern detection)

    Returns:
        Same decisions list, each augmented with an ``enrichment`` dict.
        Never removes or mutates any existing decision field.
        Fail-open: if enrichment fails for a decision, it is returned unchanged.
    """
    if not decisions:
        return decisions

    groups = _build_groups(validated_events)

    enriched: list[dict[str, Any]] = []
    for decision in decisions:
        d = {**decision}   # shallow copy — preserve all existing fields

        try:
            # Reconstruct the signal subset relevant to this decision
            decision_metrics = {m.lower() for m in d.get("signals", [])}
            relevant = [
                e for e in validated_events
                if e.get("metric", "").lower() in decision_metrics
            ] if decision_metrics else validated_events

            pattern_id, pattern_desc = _detect_structural_pattern(groups, validated_events)

            d["enrichment"] = {
                "fact":       _build_fact(d, relevant),
                "pattern":    _build_pattern(d, groups, relevant, pattern_id, pattern_desc),
                "impact":     _build_impact(pattern_id, d),
                "action":     _build_action(pattern_id, d),
                "hypothesis": _build_hypothesis(pattern_id, d, relevant),
                "pattern_id": pattern_id,
            }

        except Exception:
            # Fail-open: enrich what we can, never break the pipeline
            d.setdefault("enrichment", {})

        enriched.append(d)

    return enriched
