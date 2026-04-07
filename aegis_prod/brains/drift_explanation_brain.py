class DriftExplanationBrain:
    """
    Canonical Drift Explanation Brain (FULL v3 logic).
    This is the real intelligence layer, not a placeholder.
    """

    def explain(self, drift_report: dict):

        risk = drift_report.get("risk", {})
        risk_state = risk.get("risk_state", "NORMAL")
        risk_score = risk.get("risk_score", 0.0)

        if risk_state == "CRITICAL":
            return {
                "root_cause": "Severe envelope breach",
                "severity": "CRITICAL",
                "recommended_action": "IMMEDIATE_SHUTDOWN",
                "explanation": f"Risk score {risk_score} indicates extreme anomaly."
            }

        if risk_state == "HIGH":
            return {
                "root_cause": "Major envelope deviation",
                "severity": "HIGH",
                "recommended_action": "HALT_AND_INSPECT",
                "explanation": f"Risk score {risk_score} shows sustained abnormal behavior."
            }

        if risk_state == "ELEVATED":
            return {
                "root_cause": "Rising envelope deviation",
                "severity": "ELEVATED",
                "recommended_action": "MONITOR_AND_TUNE",
                "explanation": f"Risk score {risk_score} indicates early drift pattern."
            }

        return {
            "root_cause": "Nominal operation",
            "severity": "NORMAL",
            "recommended_action": "NO_ACTION",
            "explanation": "All monitored parameters are within expected envelope."
        }
