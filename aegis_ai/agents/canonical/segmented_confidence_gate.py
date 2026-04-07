# aegis_ai/agents/segmented_confidence_gate.py

from typing import Dict, Any


class SegmentedConfidenceGate:
    """
    Canonical Confidence Gate.

    Computes deterministic confidence level
    from current structured signals only.

    No history.
    No insight filtering.
    No time dependency.
    """

    def run(self, state: Dict[str, Any]) -> None:

        intelligence = state.setdefault("intelligence", {})

        drift = state.get("drift_report", {}) or {}
        quality = state.get("quality_report", {}) or {}
        regime = intelligence.get("regime", {})

        drift_magnitude = float(drift.get("magnitude", 0.0) or 0.0)
        quality_score = float(quality.get("score", 1.0) or 1.0)
        stress = regime.get("stress", "NORMAL")

        score = 1.0

        # Quality impact
        if quality_score <= 0.5:
            score -= 0.4
        elif quality_score <= 0.7:
            score -= 0.2

        # Drift impact
        if drift_magnitude >= 0.5:
            score -= 0.3
        elif drift_magnitude >= 0.3:
            score -= 0.15

        # Stress impact
        if stress == "STRESSED":
            score -= 0.1

        # Clamp between 0 and 1
        score = max(0.0, min(1.0, score))

        if score >= 0.75:
            level = "HIGH"
        elif score >= 0.5:
            level = "MEDIUM"
        else:
            level = "LOW"

        intelligence["confidence"] = {
            "score": round(score, 3),
            "level": level,
        }
