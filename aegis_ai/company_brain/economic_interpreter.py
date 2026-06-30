"""
aegis_ai/company_brain/economic_interpreter.py
===============================================
Phase 2: Deterministic economic interpretation layer.

Converts raw signal direction + metric polarity into economically
meaningful language. NO ML, NO recommendations, NO advice — only
factual interpretation of what the data says.

Polarity rules:
  GOOD_UP  + UPWARD   → improvement
  GOOD_UP  + DOWNWARD → deterioration
  GOOD_DOWN + UPWARD  → deterioration  (e.g., costs rising = bad)
  GOOD_DOWN + DOWNWARD → improvement   (e.g., defects falling = good)
  STRUCTURAL           → concentration (no direction)
"""

from __future__ import annotations

import re
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# POLARITY INFERENCE (reuses F-02 logic)
# ─────────────────────────────────────────────────────────────────────────────

_POLARITY_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?:^|_|\b)(revenue|sales|income|turnover|profit|margin|roi|roas|conversion|cvr|ctr|nps|clv|satisfaction|rating|score|efficiency|performance|output|volume|units|quantity|qty|orders|bookings|signups|fill.?rate|oee|on.?time|yield)(?:$|_|\b)", re.I), "GOOD_UP"),
    (re.compile(r"(?:^|_|\b)(cost|expense|spend|cogs|opex|capex|overhead|defect|churn|attrition|return|refund|downtime|absence|error|fault|reject|complaint|incident|delay|late|overdue|cpa|cac|burn)(?:$|_|\b)", re.I), "GOOD_DOWN"),
    (re.compile(r"(?:^|_|\b)(transfer|inventory|stock|warehouse|movement|logistics|freight|shipping|headcount|fte|count)(?:$|_|\b)", re.I), "NEUTRAL"),
]


def infer_polarity(metric_name: str) -> str:
    """Returns GOOD_UP | GOOD_DOWN | NEUTRAL | UNKNOWN."""
    for pattern, polarity in _POLARITY_KEYWORDS:
        if pattern.search(metric_name):
            return polarity
    return "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
# DIRECTIONAL MEANING
# ─────────────────────────────────────────────────────────────────────────────

_INTERPRETATION_MAP = {
    ("GOOD_UP",   "UPWARD"):   ("improvement",    "positive"),
    ("GOOD_UP",   "DOWNWARD"): ("deterioration",  "negative"),
    ("GOOD_DOWN", "UPWARD"):   ("deterioration",  "negative"),
    ("GOOD_DOWN", "DOWNWARD"): ("improvement",    "positive"),
    ("NEUTRAL",   "UPWARD"):   ("increase",       "neutral"),
    ("NEUTRAL",   "DOWNWARD"): ("decrease",       "neutral"),
    ("UNKNOWN",   "UPWARD"):   ("increase",       "neutral"),
    ("UNKNOWN",   "DOWNWARD"): ("decrease",       "neutral"),
}

_ECONOMIC_LABELS = {
    ("GOOD_UP",   "UPWARD"):   "growth signal",
    ("GOOD_UP",   "DOWNWARD"): "demand contraction",
    ("GOOD_DOWN", "UPWARD"):   "cost pressure",
    ("GOOD_DOWN", "DOWNWARD"): "efficiency gain",
    ("NEUTRAL",   "UPWARD"):   "volume increase",
    ("NEUTRAL",   "DOWNWARD"): "volume decrease",
}


def interpret_direction(metric: str, direction: str) -> dict[str, str]:
    """
    Given a metric name and its detected direction, return the
    economic interpretation.

    Returns:
        {
            "polarity":      "GOOD_UP" | "GOOD_DOWN" | "NEUTRAL" | "UNKNOWN",
            "meaning":       "improvement" | "deterioration" | "increase" | "decrease",
            "sentiment":     "positive" | "negative" | "neutral",
            "economic_label": "growth signal" | "cost pressure" | etc.,
        }
    """
    polarity = infer_polarity(metric)

    if direction == "STRUCTURAL":
        return {
            "polarity": polarity,
            "meaning": "concentration",
            "sentiment": "neutral",
            "economic_label": "structural concentration risk",
        }

    key = (polarity, direction)
    meaning, sentiment = _INTERPRETATION_MAP.get(key, ("change", "neutral"))
    label = _ECONOMIC_LABELS.get(key, "structural change")

    return {
        "polarity": polarity,
        "meaning": meaning,
        "sentiment": sentiment,
        "economic_label": label,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CONFIDENCE EXPLANATION
# ─────────────────────────────────────────────────────────────────────────────

def explain_confidence(confidence: float, metadata: dict[str, Any] | None = None) -> str:
    """
    Generate a human-readable explanation for WHY confidence is at its level.
    No magic numbers — explains what contributed to the score.
    """
    meta = metadata or {}
    parts: list[str] = []

    if confidence >= 0.85:
        level = "high"
    elif confidence >= 0.6:
        level = "moderate"
    elif confidence >= 0.4:
        level = "low"
    else:
        level = "very low"

    parts.append(f"Confidence is {level} ({confidence:.0%})")

    maturity = meta.get("baseline_maturity")
    if maturity == "IMMATURE":
        parts.append("baseline is immature (fewer than 2 uploads)")
    elif maturity == "DEVELOPING":
        parts.append("baseline is still developing (fewer than 5 uploads)")

    upload_count = meta.get("upload_count")
    if upload_count is not None and upload_count < 5:
        parts.append(f"based on {upload_count} data upload(s)")

    return ". ".join(parts) + "."


# ─────────────────────────────────────────────────────────────────────────────
# DECISION ENRICHMENT — attach economic interpretation to each decision
# ─────────────────────────────────────────────────────────────────────────────

def enrich_with_economics(
    decisions: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Attach economic interpretation to each decision.
    Deterministic. No ML. No recommendations.
    Adds 'economic_interpretation' block to each decision.
    """
    enriched: list[dict[str, Any]] = []

    for d in decisions:
        d = {**d}  # shallow copy

        signals = d.get("signals", [])
        direction = _infer_decision_direction(d)
        primary_metric = signals[0] if signals else ""

        interp = interpret_direction(primary_metric, direction)
        conf_explanation = explain_confidence(
            d.get("confidence", 0.0), metadata
        )

        d["economic_interpretation"] = {
            "directional_meaning": interp["meaning"],
            "sentiment": interp["sentiment"],
            "economic_label": interp["economic_label"],
            "polarity": interp["polarity"],
            "confidence_explanation": conf_explanation,
            "root_signal_type": d.get("type", "UNKNOWN"),
        }

        enriched.append(d)

    return enriched


def _infer_decision_direction(decision: dict[str, Any]) -> str:
    """Infer the dominant direction from a decision's type and title."""
    dtype = decision.get("type", "")
    title = decision.get("title", "")

    if dtype == "CONCENTRATION_RISK":
        return "STRUCTURAL"

    if "Declining" in title or "Deteriorat" in title or "decline" in dtype.lower():
        return "DOWNWARD"
    if "Growth" in title or "Improving" in title or "Rising" in title or "gain" in dtype.lower():
        return "UPWARD"

    # Fallback: look for direction words in summary
    summary = decision.get("summary", "").lower()
    if "declining" in summary or "decreasing" in summary or "falling" in summary:
        return "DOWNWARD"
    if "rising" in summary or "increasing" in summary or "growing" in summary:
        return "UPWARD"

    return "UNKNOWN"
