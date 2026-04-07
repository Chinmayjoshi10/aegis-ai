# aegis_ai/agents/segmented_tradeoff_detector.py

from typing import Dict, Any


class SegmentedTradeoffDetector:
    """
    Canonical Tradeoff Detector.

    Detects contradictory behavioral signals in current snapshot only.

    No history.
    No insights.
    No narratives.
    No list growth.
    Deterministic.
    """

    def run(self, state: Dict[str, Any]) -> None:

        intelligence = state.setdefault("intelligence", {})

        regime = intelligence.get("regime", {})
        escalation = intelligence.get("escalation", {})
        confidence = intelligence.get("confidence", {})

        stress = regime.get("stress")
        severity = escalation.get("severity")
        confidence_level = confidence.get("level")

        tradeoff_flags = []

        # Tradeoff 1: High stress but LOW severity
        if stress == "STRESSED" and severity == "LOW":
            tradeoff_flags.append("UNDER_REACTING_UNDER_STRESS")

        # Tradeoff 2: Critical severity but HIGH confidence
        if severity == "CRITICAL" and confidence_level == "HIGH":
            tradeoff_flags.append("OVERCONFIDENT_UNDER_CRISIS")

        # Tradeoff 3: Low quality but LOW escalation
        quality = state.get("quality_report", {})
        quality_score = float(quality.get("score", 1.0) or 1.0)

        if quality_score <= 0.6 and severity == "LOW":
            tradeoff_flags.append("QUALITY_IGNORED")

        if tradeoff_flags:
            intelligence["tradeoffs"] = {
                "flags": tradeoff_flags,
                "count": len(tradeoff_flags),
            }
        else:
            intelligence["tradeoffs"] = {
                "flags": [],
                "count": 0,
            }
