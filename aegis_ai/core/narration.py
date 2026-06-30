"""
aegis_ai/core/narration.py
============================
Narration Layer — converts AEGIS structured output into plain English.

Design:
  - Input: ONLY the structured JSON from compose_structured_output()
  - No access to raw data, df, brain_output, or pipeline internals
  - No independent reasoning — reads and translates, never invents

Modes:
  "template"  — deterministic, production-ready (DEFAULT)
  "llm"       — uses Gemma via Ollama, falls back to template on error

Template mode produces 4 sections:
  1. State Summary    — one sentence from state + meta
  2. Signal Summary   — top 3 signals by confidence
  3. Decision Summary — top 3 decisions by rank
  4. Data Quality     — warning if score < 0.8 or state == DATA_ISSUE
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("aegis_ai.core.narration")


# ─────────────────────────────────────────────────────────────────────────────
# LLM MODE — Gemma integration via Ollama
# ─────────────────────────────────────────────────────────────────────────────

_NARRATION_SYSTEM_PROMPT = """You are AEGIS, a deterministic decision intelligence engine.
Generate a clear, professional narration of the analysis results below.

RULES:
- Use ONLY the information in the provided JSON
- Do NOT invent new insights, predictions, or metrics
- Do NOT reference data you were not given
- Include the headline in your narration
- Structure: state summary, key signals, recommended actions, data quality (if relevant)
- Keep it concise (3-5 paragraphs)
- Write in third person ("AEGIS detected...")
"""


def _llm_narration(aegis_output: dict[str, Any]) -> str:
    """
    LLM-based narration via Gemma/Ollama.

    Gemma receives ONLY the structured JSON — never raw data.
    On any failure, the caller falls back to template mode.
    """
    from aegis_ai.llm.call_gemma import call_gemma

    # Build a focused context (exclude heavy nested objects for token efficiency)
    context = {
        "state":        aegis_output.get("state"),
        "state_reason": aegis_output.get("state_reason"),
        "headline":     aegis_output.get("headline"),
        "confidence":   aegis_output.get("confidence"),
        "signals":      aegis_output.get("signals", [])[:3],
        "decisions":    aegis_output.get("decisions", [])[:3],
        "data_quality": aegis_output.get("data_quality", {}),
        "root_cause":   aegis_output.get("root_cause", {}),
        "action":       aegis_output.get("action"),
        "meta": {
            "domain":    aegis_output.get("meta", {}).get("domain"),
            "row_count": aegis_output.get("meta", {}).get("row_count"),
        },
    }

    prompt = (
        f"{_NARRATION_SYSTEM_PROMPT}\n\n"
        f"ANALYSIS JSON:\n{json.dumps(context, indent=2, default=str)}\n\n"
        f"Generate the narration:"
    )

    return call_gemma(prompt, timeout=180)


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE MODE — deterministic, production-ready
# ─────────────────────────────────────────────────────────────────────────────

def _template_narration(aegis_output: dict[str, Any]) -> str:
    """
    Build a deterministic, multi-paragraph narration from structured JSON.
    Same input → same output every time.
    """
    sections: list[str] = []

    # ── Section 1: State Summary ──────────────────────────────────────────
    sections.append(_section_state(aegis_output))

    # ── Section 2: Signal Summary ─────────────────────────────────────────
    signal_text = _section_signals(aegis_output)
    if signal_text:
        sections.append(signal_text)

    # ── Section 3: Decision Summary ───────────────────────────────────────
    decision_text = _section_decisions(aegis_output)
    if decision_text:
        sections.append(decision_text)

    # ── Section 4: Data Quality Warning ───────────────────────────────────
    quality_text = _section_data_quality(aegis_output)
    if quality_text:
        sections.append(quality_text)

    return "\n\n".join(sections)


# ─────────────────────────────────────────────────────────────────────────────
# NARRATION SECTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _section_state(output: dict[str, Any]) -> str:
    """Section 1: State summary — one sentence from state + meta."""
    state    = output.get("state", "NO_SIGNAL")
    meta     = output.get("meta", {})
    domain   = meta.get("domain", "the dataset")
    row_count = meta.get("row_count", 0)
    n_metrics = len(meta.get("metrics_analyzed", []))
    confidence = output.get("confidence", 0.0)
    headline = output.get("headline", "")

    if state == "DATA_ISSUE":
        return (
            f"AEGIS analyzed {row_count:,} rows of {domain} data across "
            f"{n_metrics} metrics but encountered significant data quality issues. "
            f"{headline}. Signals cannot be reliably interpreted until data quality is resolved."
        )

    if state == "NO_SIGNAL":
        return (
            f"AEGIS analyzed {row_count:,} rows of {domain} data across "
            f"{n_metrics} metrics and found no structural patterns "
            f"that meet the confidence threshold. "
            f"The system is operating within expected parameters."
        )

    if state == "MIXED":
        return (
            f"AEGIS analyzed {row_count:,} rows of {domain} data and detected "
            f"structural patterns, but data quality is degraded "
            f"(confidence: {confidence:.0%}). "
            f"{headline}."
        )

    # ACTIONABLE
    return (
        f"AEGIS analyzed {row_count:,} rows of {domain} data across "
        f"{n_metrics} metrics and identified actionable structural patterns "
        f"with {confidence:.0%} aggregate confidence. "
        f"{headline}."
    )


def _section_signals(output: dict[str, Any]) -> str:
    """
    Section 2: All signals — never dropped silently.

    Headlines the top 3 by confidence, then appends a one-line roll-up for
    the remainder so no metric disappears from the narration.
    """
    signals = output.get("signals", [])
    if not signals:
        return ""

    # Already sorted by confidence in structured_output.
    top_signals       = signals[:3]
    remaining_signals = signals[3:]

    lines = ["Key signals detected:"]
    for s in top_signals:
        metric     = s.get("metric", "A metric")
        direction  = s.get("direction", "FLAT")
        # Prefer signal_confidence (calibrated per direction) when present.
        conf       = s.get("signal_confidence", s.get("confidence", 0.0))
        primitive  = s.get("primitive", "")
        # Cap magnitude in narration too — even if upstream forgot, no line
        # should ever print "448% magnitude".
        raw_mag    = s.get("magnitude_pct", 0.0)
        mag        = min(abs(float(raw_mag or 0.0)), 200.0)

        # Build direction phrase (uses canonical enum: UP, DOWN, FLAT, STRUCTURAL)
        dir_phrases = {
            "UP":         "trending upward",
            "DOWN":       "trending downward",
            "STRUCTURAL": "showing structural concentration",
            "FLAT":       "stable with no significant movement",
        }
        dir_phrase = dir_phrases.get(direction, "showing a detected change")

        # Magnitude qualifier is only meaningful when there is movement.
        mag_phrase = ""
        if direction != "FLAT" and mag and abs(mag) > 0.1:
            display_mag = min(abs(mag), 100.0)
            mag_phrase = f" ({display_mag:.1f}% magnitude)"

        # Build primitive context — suppress drift language for FLAT signals.
        prim_phrases = {
            "BIAS":      " — persistent drift from baseline",
            "DOMINANCE": " — structural concentration detected",
            "TRADEOFF":  " — structural tradeoff",
            "STABLE":    " — stability confirmed",
            "NONE":      "",
        }
        prim_phrase = prim_phrases.get(primitive, "")
        if direction == "FLAT" and primitive == "BIAS":
            # Safety net: should not occur after _reconcile_flat_signal, but
            # we never want the contradiction "stable … persistent drift".
            prim_phrase = " — stability confirmed"

        lines.append(
            f"  • {metric} is {dir_phrase}{mag_phrase} "
            f"({conf:.0%} confidence){prim_phrase}"
        )

    # Roll-up so downstream signals are never silently dropped.
    if remaining_signals:
        extras = ", ".join(
            f"{s.get('metric', 'metric')} "
            f"({s.get('direction', 'FLAT').lower()}, "
            f"{s.get('signal_confidence', s.get('confidence', 0.0)):.0%})"
            for s in remaining_signals
        )
        lines.append(f"  • Additional signals: {extras}")

    return "\n".join(lines)


def _section_decisions(output: dict[str, Any]) -> str:
    """Section 3: Top 3 decisions by rank."""
    decisions = output.get("decisions", [])
    if not decisions:
        return ""

    lines = ["Recommended actions:"]
    for d in decisions[:3]:
        rank     = d.get("rank", "")
        title    = d.get("title", "")
        action   = d.get("action", "")
        priority = d.get("priority", "MEDIUM")
        conf     = d.get("confidence", 0.0)

        action_display = action if action else "Investigate further"
        lines.append(
            f"  {rank}. [{priority}] {title} — {action_display} "
            f"(confidence: {conf:.0%})"
        )

    return "\n".join(lines)


def _section_data_quality(output: dict[str, Any]) -> str:
    """Section 4: Data quality warning — only if quality is degraded."""
    dq    = output.get("data_quality", {})
    state = output.get("state", "")
    score = float(dq.get("score", 1.0))

    # Only emit if quality is actually problematic
    if score >= 0.8 and state != "DATA_ISSUE":
        return ""

    parts = [f"Data quality score: {score:.0%}."]

    warnings = dq.get("warnings", [])
    for w in warnings[:3]:
        parts.append(f"  ⚠ {w}")

    notes = dq.get("notes", [])
    for n in notes[:3]:
        parts.append(f"  ⚠ {n}")

    missing = dq.get("missing_columns", {})
    high_missing = {k: v for k, v in missing.items() if float(v) > 0.1}
    if high_missing:
        cols = ", ".join(f"{k} ({v:.0%})" for k, v in sorted(
            high_missing.items(), key=lambda x: -x[1]
        )[:3])
        parts.append(f"  High missing rates: {cols}")

    violations = dq.get("domain_violations", {})
    if violations:
        cols = ", ".join(f"{k} ({v} rows)" for k, v in violations.items())
        parts.append(f"  Domain violations: {cols}")

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# HEADLINE VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def _verify_headline(narration: str, aegis_output: dict[str, Any]) -> bool:
    """
    Check that the headline is genuinely represented in the narration.

    Previous implementation used a strict case-sensitive substring match,
    which returned False even when the narration correctly stated the
    headline with different casing, whitespace, or trailing punctuation —
    producing spurious `headline_verified=false` in narration_meta.

    New rule: normalize both strings (casefold, collapse whitespace, strip
    trailing punctuation) before comparing. An empty or whitespace-only
    narration is never considered "verified".
    """
    headline = (aegis_output.get("headline") or "").strip()
    if not headline:
        return True  # no headline to verify

    narration_text = (narration or "").strip()
    if not narration_text:
        return False

    def _norm(s: str) -> str:
        # casefold + collapse whitespace + strip trailing punctuation
        collapsed = " ".join(s.split()).casefold()
        return collapsed.rstrip(".!?,;: ")

    return _norm(headline) in _norm(narration_text)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def generate_narration(
    aegis_output: dict[str, Any],
    mode: str = "template",
) -> str:
    """
    Convert AEGIS structured output into plain English narration.

    Args:
        aegis_output: The full structured output dict from compose_structured_output()
        mode: "template" (default, deterministic) or "llm" (Gemma via Ollama)

    Returns:
        str: Multi-paragraph narration text

    Raises:
        ValueError: If mode is not recognized
    """
    used_fallback = False

    if mode == "template":
        narration = _template_narration(aegis_output)

    elif mode == "llm":
        try:
            narration = _llm_narration(aegis_output)
        except Exception as e:
            log.warning(f"[NARRATION] LLM narration failed: {e}, falling back to template")
            narration = _template_narration(aegis_output)
            used_fallback = True
    else:
        raise ValueError(f"Unknown narration mode: {mode!r}. Use 'template' or 'llm'.")

    # Headline verification — log warning if headline is missing from narration
    if not _verify_headline(narration, aegis_output):
        headline = aegis_output.get("headline", "")
        log.warning(
            f"[NARRATION] Headline not found in narration. "
            f"headline='{headline}' mode={mode} fallback={used_fallback}"
        )

    return narration


def build_narration_meta(
    aegis_output: dict[str, Any],
    narration_text: str,
    mode: str = "template",
    used_fallback: bool = False,
) -> dict[str, Any]:
    """
    Build narration metadata block for API response.
    Called at the API layer, not inside generate_narration().

    Returns:
        dict with mode, fallback status, and headline verification
    """
    return {
        "mode":              mode,
        "fallback":          used_fallback,
        "headline_verified": _verify_headline(narration_text, aegis_output),
    }
