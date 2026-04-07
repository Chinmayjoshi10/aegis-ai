class GuardrailBrain:
    """
    Decision firewall for AEGIS.
    Blocks unsafe, impossible, or dangerous autonomous actions.
    """

    MAX_RISK = 0.6
    MAX_DRIFT = 0.8

    def validate(self, state: dict):
        risk = state.get("risk", {}).get("risk_score", 0)
        drift = state.get("future_drift_risk", 0)

        if risk > self.MAX_RISK:
            return self._block("RISK_THRESHOLD_EXCEEDED", risk)

        if drift > self.MAX_DRIFT:
            return self._block("PREDICTED_INSTABILITY", drift)

        return {"approved": True}

    def _block(self, reason, value):
        return {
            "approved": False,
            "reason": reason,
            "value": value
        }
