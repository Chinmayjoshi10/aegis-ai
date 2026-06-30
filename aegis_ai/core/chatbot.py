"""
aegis_ai/core/chatbot.py
===========================
Grounded Chatbot — answers questions using ONLY the AEGIS structured output.

Design:
  - Input: user question + structured JSON (from compose_structured_output())
  - Gemma receives a strictly constrained prompt with ONLY the JSON
  - No raw data access, no independent reasoning
  - If Gemma unavailable → deterministic keyword-based fallback
  - If answer not in JSON → explicit refusal

This module NEVER:
  - Accesses the raw dataset
  - Generates new insights or predictions
  - Makes claims not present in the structured output
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("aegis_ai.core.chatbot")

_SYSTEM_PROMPT = """You are AEGIS, a decision intelligence assistant.
You answer questions using ONLY the provided JSON analysis.

STRICT RULES:
1. Use ONLY information present in the JSON below
2. Do NOT invent new insights, predictions, or data
3. Do NOT reference external knowledge or assumptions
4. If the answer is not available in the JSON, say: "This information is not available in the current analysis."
5. Be concise and factual
6. Reference specific metrics, signals, or decisions from the JSON when answering
"""

_REFUSAL = "This information is not available in the current analysis."


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL TRACEABILITY — which signals informed the answer
# ─────────────────────────────────────────────────────────────────────────────

def _extract_signals_used(
    answer: str,
    aegis_output: dict[str, Any],
) -> list[str]:
    """
    Extract signal IDs that are referenced in the answer.
    Checks if signal metrics appear in the answer text.
    """
    signals = aegis_output.get("signals", [])
    used = []
    answer_lower = answer.lower()
    for s in signals:
        metric = s.get("metric", "")
        if metric and metric.lower() in answer_lower:
            sid = s.get("id", "")
            if sid:
                used.append(sid)
    return used


# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD FALLBACK — deterministic, no LLM needed
# ─────────────────────────────────────────────────────────────────────────────

def _keyword_fallback(question: str, aegis_output: dict[str, Any]) -> str:
    """
    Simple keyword-matching fallback when Gemma is unavailable.
    Deterministic: same question + same JSON → same answer.
    """
    q = question.lower().strip()

    # State / status queries
    if any(w in q for w in ["state", "status", "health", "overall"]):
        state = aegis_output.get("state", "UNKNOWN")
        headline = aegis_output.get("headline", "")
        reason = aegis_output.get("state_reason", {}).get("primary", "")
        return f"Current state: {state}. {headline}. {reason}"

    # Signal / trend queries
    if any(w in q for w in ["signal", "trend", "direction", "moving"]):
        signals = aegis_output.get("signals", [])
        if not signals:
            return "No signals were detected in this analysis."
        lines = ["Detected signals:"]
        for s in signals[:3]:
            lines.append(
                f"  • {s.get('metric', '?')}: {s.get('direction', '?')} "
                f"({s.get('confidence', 0):.0%} confidence, "
                f"{s.get('primitive', '?')} pattern)"
            )
        return "\n".join(lines)

    # Decision / action queries
    if any(w in q for w in ["decision", "action", "recommend", "what should", "do"]):
        decisions = aegis_output.get("decisions", [])
        if not decisions:
            return "No actionable decisions were generated."
        lines = ["Top recommendations:"]
        for d in decisions[:3]:
            lines.append(
                f"  {d.get('rank', '?')}. [{d.get('priority', '?')}] "
                f"{d.get('title', '?')} — {d.get('action', '?')}"
            )
        return "\n".join(lines)

    # Quality queries
    if any(w in q for w in ["quality", "data quality", "missing", "issue"]):
        dq = aegis_output.get("data_quality", {})
        score = dq.get("score", 0)
        status = dq.get("overall_status", "UNKNOWN")
        return f"Data quality score: {score:.0%}, status: {status}."

    # Confidence queries
    if any(w in q for w in ["confidence", "confident", "how sure", "certain", "reliable"]):
        conf = aegis_output.get("confidence", 0)
        state = aegis_output.get("state", "UNKNOWN")
        return (
            f"Aggregate confidence: {conf:.0%} (state: {state}). "
            f"Confidence is weighted by decision strength and data quality."
        )

    # Root cause queries
    if any(w in q for w in ["root cause", "why", "driver", "cause"]):
        rc = aegis_output.get("root_cause", {})
        summary = rc.get("summary", "")
        driver = rc.get("primary_driver", "")
        if summary:
            return f"Root cause: {summary}. Primary driver: {driver}."
        return _REFUSAL

    # Metric-specific queries — check if the question mentions a known metric
    metrics_analyzed = aegis_output.get("meta", {}).get("metrics_analyzed", [])
    for metric in metrics_analyzed:
        if metric.lower() in q:
            # Find this metric in signals
            for s in aegis_output.get("signals", []):
                if s.get("metric", "").lower() == metric.lower():
                    return (
                        f"{s['metric']}: direction={s.get('direction', '?')}, "
                        f"magnitude={s.get('magnitude_pct', 0):.1f}%, "
                        f"confidence={s.get('confidence', 0):.0%}, "
                        f"pattern={s.get('primitive', '?')}"
                    )
            return f"{metric} was analyzed but no significant signal was detected."

    # Default: cannot determine from keywords
    return _REFUSAL


# ─────────────────────────────────────────────────────────────────────────────
# LLM-BASED ANSWER — Gemma via Ollama
# ─────────────────────────────────────────────────────────────────────────────

def _llm_answer(question: str, aegis_output: dict[str, Any]) -> str:
    """
    Answer using Gemma. The LLM sees ONLY the structured JSON.
    """
    from aegis_ai.llm.call_gemma import call_gemma

    # Build focused context (exclude heavy nested objects for token efficiency)
    context = {
        "state":        aegis_output.get("state"),
        "state_reason": aegis_output.get("state_reason"),
        "headline":     aegis_output.get("headline"),
        "confidence":   aegis_output.get("confidence"),
        "signals":      aegis_output.get("signals", []),
        "decisions":    aegis_output.get("decisions", []),
        "data_quality": aegis_output.get("data_quality", {}),
        "root_cause":   aegis_output.get("root_cause", {}),
        "action":       aegis_output.get("action"),
        "assumptions":  aegis_output.get("assumptions", []),
        "limitations":  aegis_output.get("limitations", []),
        "meta": {
            "domain":            aegis_output.get("meta", {}).get("domain"),
            "row_count":         aegis_output.get("meta", {}).get("row_count"),
            "metrics_analyzed":  aegis_output.get("meta", {}).get("metrics_analyzed"),
            "baseline_maturity": aegis_output.get("meta", {}).get("baseline_maturity"),
        },
    }

    prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"ANALYSIS JSON:\n{json.dumps(context, indent=2, default=str)}\n\n"
        f"USER QUESTION: {question}\n\n"
        f"ANSWER:"
    )

    return call_gemma(prompt, timeout=180)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def answer_question(
    question: str,
    aegis_output: dict[str, Any],
) -> dict[str, Any]:
    """
    Answer a natural language question using ONLY the structured JSON.

    Tries Gemma first; falls back to keyword matching if unavailable.

    Args:
        question: The user's question
        aegis_output: The structured output from compose_structured_output()

    Returns:
        dict with: answer, grounded (bool), source (str), mode (str)
    """
    if not question or not question.strip():
        return {
            "answer":   "Please provide a question.",
            "grounded": True,
            "source":   "validation",
            "mode":     "none",
        }

    # Try LLM first
    try:
        from aegis_ai.llm.call_gemma import is_gemma_available

        if is_gemma_available():
            answer = _llm_answer(question, aegis_output)
            return {
                "answer":       answer,
                "grounded":     True,
                "source":       "gemma",
                "mode":         "llm",
                "signals_used": _extract_signals_used(answer, aegis_output),
            }
    except Exception as e:
        log.warning(f"[CHATBOT] Gemma failed: {e}, using keyword fallback")

    # Keyword fallback
    answer = _keyword_fallback(question, aegis_output)
    return {
        "answer":       answer,
        "grounded":     True,
        "source":       "keyword_fallback",
        "mode":         "template",
        "signals_used": _extract_signals_used(answer, aegis_output),
    }
