"""
aegis_ai/core/cross_validator.py
================================
Domain-aware cross-validation layer.

Combines generic metric relationships with domain-specific business
rules to validate, support, or challenge decisions produced by the
decision pipeline.

Contract:
  - Never removes decisions
  - Only adjusts confidence and attaches validation metadata
  - Deterministic: same inputs → same outputs
  - Fail-open: validator errors → return decisions unchanged
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("aegis_ai.core.cross_validator")

_CONFIDENCE_BOOST = 0.15
_CONFIDENCE_PENALTY = 0.25


# ─────────────────────────────────────────────────────────────────────────────
# GENERIC METRIC RELATIONSHIPS (domain-agnostic)
# ─────────────────────────────────────────────────────────────────────────────

_GENERIC_RELATIONSHIPS: list[dict[str, Any]] = [
    # revenue ↔ profit: both up = supported, diverging = conflict
    {"a": r"revenue|sales|income",     "b": r"profit|margin|earnings",   "relation": "POSITIVE"},
    # cost ↔ profit: inverse
    {"a": r"cost|expense|spend",       "b": r"profit|margin|earnings",   "relation": "NEGATIVE"},
    # volume ↔ revenue
    {"a": r"volume|quantity|units",    "b": r"revenue|sales|income",     "relation": "POSITIVE"},
    # delay ↔ delivery risk
    {"a": r"delay|late|overdue",       "b": r"delivery|shipping|lead_time", "relation": "POSITIVE"},
    # conversion ↔ revenue
    {"a": r"conversion|cvr|conv",      "b": r"revenue|sales|income",     "relation": "POSITIVE"},
    # price ↔ price/amount: correlated
    {"a": r"price|pricing",            "b": r"amount|total|order.*value", "relation": "POSITIVE"},
    # price ↔ revenue
    {"a": r"price|pricing",            "b": r"revenue|sales|income",     "relation": "POSITIVE"},
    # cost ↔ price
    {"a": r"cost|expense|spend",       "b": r"price|pricing",            "relation": "POSITIVE"},
]


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN-SPECIFIC RULES
# ─────────────────────────────────────────────────────────────────────────────

_DOMAIN_RULES: dict[str, list[dict[str, Any]]] = {

    "marketing": [
        # CTR ↑ but Conversion ↓ → poor targeting
        {"a": r"ctr|click.?rate|clicks",    "a_dir": "UPWARD",
         "b": r"conversion|cvr|conv",        "b_dir": "DOWNWARD",
         "label": "poor_targeting",          "effect": "CONFLICTING"},
        # Spend ↑ but Revenue ↓ → inefficiency
        {"a": r"spend|cost|budget",          "a_dir": "UPWARD",
         "b": r"revenue|sales|income",       "b_dir": "DOWNWARD",
         "label": "ad_inefficiency",         "effect": "CONFLICTING"},
        # Impressions ↑ but CTR ↓ → creative fatigue
        {"a": r"impression|views|reach",     "a_dir": "UPWARD",
         "b": r"ctr|click.?rate",            "b_dir": "DOWNWARD",
         "label": "creative_fatigue",        "effect": "CONFLICTING"},
        # CTR ↑ and Conversion ↑ → strong funnel
        {"a": r"ctr|click.?rate",            "a_dir": "UPWARD",
         "b": r"conversion|cvr|conv",        "b_dir": "UPWARD",
         "label": "strong_funnel",           "effect": "SUPPORTING"},
    ],

    "supply_chain": [
        # Delay ↑ AND late delivery risk ↑ → supported risk
        {"a": r"delay|late|overdue",         "a_dir": "UPWARD",
         "b": r"delivery.?risk|late.?delivery|shipping.?risk", "b_dir": "UPWARD",
         "label": "delivery_risk_confirmed", "effect": "SUPPORTING"},
        # Shipping cost ↑ but delivery time not improving
        {"a": r"shipping.?cost|freight",     "a_dir": "UPWARD",
         "b": r"delivery.?time|lead.?time",  "b_dir": "UPWARD",
         "label": "shipping_inefficiency",   "effect": "CONFLICTING"},
        # Inventory ↑ but sales not increasing
        {"a": r"inventory|stock",            "a_dir": "UPWARD",
         "b": r"sales|orders|demand",        "b_dir": "DOWNWARD",
         "label": "overstock_risk",          "effect": "CONFLICTING"},
    ],

    "finance": [
        # Revenue ↑ but Profit ↓ → margin compression
        {"a": r"revenue|sales|income",       "a_dir": "UPWARD",
         "b": r"profit|margin|net.?income",  "b_dir": "DOWNWARD",
         "label": "margin_compression",      "effect": "CONFLICTING"},
        # Cost ↑ faster than revenue
        {"a": r"cost|expense|opex",          "a_dir": "UPWARD",
         "b": r"revenue|sales",              "b_dir": "DOWNWARD",
         "label": "cost_outpacing_revenue",  "effect": "CONFLICTING"},
        # Cash flow ↓ while revenue ↑ → liquidity issue
        {"a": r"cash.?flow|liquidity",       "a_dir": "DOWNWARD",
         "b": r"revenue|sales|income",       "b_dir": "UPWARD",
         "label": "liquidity_risk",          "effect": "CONFLICTING"},
    ],

    "sales": [
        # Orders ↑ but revenue flat → discounting
        {"a": r"order|transaction",          "a_dir": "UPWARD",
         "b": r"revenue|sales|income",       "b_dir": "DOWNWARD",
         "label": "discounting_issue",       "effect": "CONFLICTING"},
        # Revenue ↑ but customer count ↓ → dependency
        {"a": r"revenue|sales|income",       "a_dir": "UPWARD",
         "b": r"customer|client|account",    "b_dir": "DOWNWARD",
         "label": "customer_dependency",     "effect": "CONFLICTING"},
        # Orders ↑ and revenue ↑ → healthy growth
        {"a": r"order|transaction",          "a_dir": "UPWARD",
         "b": r"revenue|sales|income",       "b_dir": "UPWARD",
         "label": "healthy_growth",          "effect": "SUPPORTING"},
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL INDEX BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_signal_index(
    signals: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Build a lookup: metric_name_lower → {direction, confidence, ...}
    For TRADEOFF signals, index both metrics.
    """
    index: dict[str, dict[str, Any]] = {}
    for sig in signals:
        primitive = sig.get("primitive", "")
        direction = (
            sig.get("subtype") or sig.get("direction") or ""
        ).upper()
        confidence = float(sig.get("confidence", 0.0))

        if primitive == "TRADEOFF":
            metrics = sig.get("metrics") or []
            d = sig.get("direction", "POSITIVE")
            for m in metrics:
                index[m.lower()] = {
                    "direction": d,
                    "confidence": confidence,
                    "primitive": primitive,
                }
        else:
            metric = sig.get("metric", "")
            if metric:
                index[metric.lower()] = {
                    "direction": direction,
                    "confidence": confidence,
                    "primitive": primitive,
                }
    return index


def _normalize_metric(name: str) -> str:
    """Strip collision suffixes (_2, _3) and normalize for matching."""
    n = re.sub(r"_\d+$", "", name.lower())
    return n.replace("_", "").replace(" ", "")


def _match_pattern(metric_lower: str, pattern: str) -> bool:
    """Check if a metric name matches a regex pattern (case-insensitive)."""
    try:
        return bool(re.search(pattern, metric_lower, re.IGNORECASE))
    except re.error:
        return False


def _find_metrics_matching(
    index: dict[str, dict], pattern: str,
) -> list[tuple[str, dict]]:
    """Return all (metric, info) pairs from the index matching pattern."""
    results = []
    for metric, info in sorted(index.items()):
        normed = _normalize_metric(metric)
        if _match_pattern(normed, pattern) or _match_pattern(metric, pattern):
            results.append((metric, info))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# GENERIC CROSS-VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def _generic_validate(
    decision: dict[str, Any],
    signal_index: dict[str, dict],
) -> tuple[list[str], list[str]]:
    """
    Check generic metric relationships against all signals.
    Returns (supporting_metrics, conflicting_metrics).
    """
    supporting: list[str] = []
    conflicting: list[str] = []

    decision_signals = [s.lower() for s in decision.get("signals", [])]
    if not decision_signals:
        return supporting, conflicting

    for rel in _GENERIC_RELATIONSHIPS:
        a_matches = _find_metrics_matching(signal_index, rel["a"])
        b_matches = _find_metrics_matching(signal_index, rel["b"])

        for a_metric, a_info in a_matches:
            for b_metric, b_info in b_matches:
                if a_metric == b_metric:
                    continue
                # Decision must reference at least one of the related metrics
                if a_metric not in decision_signals and b_metric not in decision_signals:
                    continue

                a_dir = a_info.get("direction", "")
                b_dir = b_info.get("direction", "")

                if rel["relation"] == "POSITIVE":
                    if a_dir == b_dir and a_dir in ("UPWARD", "DOWNWARD"):
                        supporting.append(b_metric)
                    elif a_dir != b_dir and a_dir and b_dir:
                        conflicting.append(b_metric)
                elif rel["relation"] == "NEGATIVE":
                    if a_dir != b_dir and a_dir and b_dir:
                        supporting.append(b_metric)
                    elif a_dir == b_dir and a_dir in ("UPWARD", "DOWNWARD"):
                        conflicting.append(b_metric)

    # Self-consistency: if the decision's own signals all move the same way, support it
    decision_directions = set()
    for ds in decision_signals:
        if ds in signal_index:
            d_dir = signal_index[ds].get("direction", "")
            if d_dir in ("UPWARD", "DOWNWARD"):
                decision_directions.add(d_dir)
    if len(decision_directions) == 1 and len(decision_signals) >= 2:
        # All signals agree → self-supporting
        for ds in decision_signals:
            if ds in signal_index:
                supporting.append(ds)

    return sorted(set(supporting)), sorted(set(conflicting))


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN-SPECIFIC CROSS-VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def _domain_validate(
    decision: dict[str, Any],
    signal_index: dict[str, dict],
    domain: str,
) -> tuple[list[str], list[str], list[str]]:
    """
    Apply domain-specific rules.
    Returns (supporting_metrics, conflicting_metrics, applied_labels).
    """
    supporting: list[str] = []
    conflicting: list[str] = []
    labels: list[str] = []

    rules = _DOMAIN_RULES.get(domain, [])
    if not rules:
        return supporting, conflicting, labels

    for rule in rules:
        a_matches = _find_metrics_matching(signal_index, rule["a"])
        b_matches = _find_metrics_matching(signal_index, rule["b"])

        for a_metric, a_info in a_matches:
            a_dir = a_info.get("direction", "")
            if a_dir != rule["a_dir"]:
                continue

            for b_metric, b_info in b_matches:
                if a_metric == b_metric:
                    continue
                b_dir = b_info.get("direction", "")
                if b_dir != rule["b_dir"]:
                    continue

                # Rule fired
                if rule["effect"] == "SUPPORTING":
                    supporting.append(b_metric)
                else:
                    conflicting.append(b_metric)
                labels.append(rule["label"])

    return sorted(set(supporting)), sorted(set(conflicting)), sorted(set(labels))


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def cross_validate_decisions(
    decisions: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    domain: str,
) -> list[dict[str, Any]]:
    """
    Cross-validate decisions against all available signals using
    generic metric relationships and domain-specific business rules.

    Args:
        decisions: list of decisions from synthesize_decisions()
        signals:   list of brain insights (BIAS, DOMINANCE, TRADEOFF)
        domain:    business domain (marketing, finance, sales, supply_chain)

    Returns:
        Same decisions list with added validation metadata:
        - validation_status: SUPPORTED | CONFLICTING | UNVERIFIED
        - supporting_metrics: []
        - conflicting_metrics: []
        - domain_rules_applied: []
        - confidence: adjusted (+0.15 supported, -0.25 conflicting)

    Never removes decisions. Deterministic. Fail-open.
    """
    if not decisions:
        return decisions

    signal_index = _build_signal_index(signals)
    validated: list[dict[str, Any]] = []

    for decision in decisions:
        d = {**decision}  # shallow copy

        try:
            # Generic validation
            gen_support, gen_conflict = _generic_validate(d, signal_index)

            # Domain validation
            dom_support, dom_conflict, dom_labels = _domain_validate(
                d, signal_index, domain,
            )

            # Merge results
            all_supporting = sorted(set(gen_support + dom_support))
            all_conflicting = sorted(set(gen_conflict + dom_conflict))

            # Determine status
            if all_conflicting:
                status = "CONFLICTING"
            elif all_supporting:
                status = "SUPPORTED"
            else:
                status = "UNVERIFIED"

            # Adjust confidence
            conf = float(d.get("confidence", 0.5))
            if status == "SUPPORTED":
                conf = min(conf + _CONFIDENCE_BOOST, 1.0)
            elif status == "CONFLICTING":
                conf = max(conf - _CONFIDENCE_PENALTY, 0.0)

            d["confidence"] = round(conf, 3)
            d["validation_status"] = status
            d["supporting_metrics"] = all_supporting
            d["conflicting_metrics"] = all_conflicting
            d["domain_rules_applied"] = dom_labels

            # F-08: Removed segment-deviation confidence floor overrides.
            # Confidence adjustments are consolidated in confidence_engine.
            # Segment deviation is retained as metadata but does not mutate confidence.
            segs = d.get("segments") or []

            # Build drivers from segments
            drivers = []
            for seg in segs[:3]:
                dim = seg.get("dimension", "")
                val = seg.get("value", "")
                dev = seg.get("deviation", 0.0)
                if dim and val:
                    dev_pct = round(abs(dev) * 100)
                    direction = "higher" if dev > 0 else "lower"
                    drivers.append(f"{val} ({dim}, {dev_pct}% {direction})")
            d["drivers"] = drivers

        except Exception as e:
            log.warning(f"[CROSS_VALIDATOR] Decision validation failed: {e}")
            d["validation_status"] = "UNVERIFIED"
            d["supporting_metrics"] = []
            d["conflicting_metrics"] = []
            d["domain_rules_applied"] = []

        validated.append(d)

    return validated
