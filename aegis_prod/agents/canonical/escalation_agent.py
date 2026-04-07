from typing import Dict, Any


class EscalationAgent:
    """
    Canonical Escalation Agent.

    Deterministic.
    No I/O.
    No persistence.
    No patch execution.
    No randomness.
    """

    def run(self, state: Dict[str, Any]) -> None:

        intelligence = state.setdefault("intelligence", {})
        regime = intelligence.get("regime", {})
        drift = state.get("drift_report", {}) or {}
        quality = state.get("quality_report", {}) or {}

        # ───────── Extract Signals Safely ─────────

        drift_magnitude = float(drift.get("magnitude", 0.0) or 0.0)
        quality_score = float(quality.get("score", 1.0) or 1.0)
        stress_regime = regime.get("stress", "NORMAL")

        severity = "LOW"
        reason = "STABLE"

        # ───────── CRITICAL ─────────
        if (
            drift_magnitude >= 0.5
            or quality_score <= 0.4
            or (drift_magnitude >= 0.35 and stress_regime == "STRESSED")
        ):
            severity = "CRITICAL"

            if drift_magnitude >= 0.5:
                reason = "EXTREME_DRIFT"
            elif quality_score <= 0.4:
                reason = "QUALITY_COLLAPSE"
            else:
                reason = "DRIFT_UNDER_STRESS"

        # ───────── HIGH ─────────
        elif (
            drift_magnitude >= 0.35
            or quality_score <= 0.6
            or (stress_regime == "STRESSED" and drift_magnitude >= 0.25)
        ):
            severity = "HIGH"

            if drift_magnitude >= 0.35:
                reason = "SIGNIFICANT_DRIFT"
            elif quality_score <= 0.6:
                reason = "QUALITY_DEGRADATION"
            else:
                reason = "STRESS_DRIFT"

        # ───────── MEDIUM ─────────
        elif drift_magnitude >= 0.2 or quality_score <= 0.75:
            severity = "MEDIUM"

            if drift_magnitude >= 0.2:
                reason = "MODERATE_DRIFT"
            else:
                reason = "QUALITY_WARNING"

        # ───────── LOW (Default) ─────────
        else:
            severity = "LOW"
            reason = "STABLE"

        intelligence["escalation"] = {
            "severity": severity,
            "reason": reason,
        }
