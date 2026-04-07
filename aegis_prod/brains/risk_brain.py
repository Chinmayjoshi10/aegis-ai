class RiskBrain:
    """
    Governing Risk Cortex.
    Reads ONLY physics state and computes enterprise collapse risk.
    """

    def run(self, state: dict):
        physics = state.get("physics", {})
        risk = {}

        # Sales
        if "sales" in physics and physics["sales"].get("status") == "OK":
            risk["sales_collapse_probability"] = physics["sales"]["failure_probability"]
            risk["sales_runway_days"] = physics["sales"]["survival_runway_days"]

        # Ops
        if "ops" in physics and physics["ops"].get("status") == "OK":
            risk["ops_collapse_probability"] = physics["ops"]["failure_probability"]
            risk["ops_runway_days"] = physics["ops"]["survival_runway_days"]

        # Logistics
        if "logistics" in physics and physics["logistics"].get("status") == "OK":
            risk["logistics_collapse_probability"] = physics["logistics"]["failure_probability"]
            risk["logistics_runway_days"] = physics["logistics"]["survival_runway_days"]

        # Finance
        if "finance" in physics and physics["finance"].get("status") == "OK":
            risk["finance_collapse_probability"] = physics["finance"]["failure_probability"]
            risk["finance_runway_days"] = physics["finance"]["survival_runway_days"]

        # HR
        if "hr" in physics and physics["hr"].get("status") == "OK":
            risk["hr_collapse_probability"] = physics["hr"]["failure_probability"]
            risk["hr_runway_days"] = physics["hr"]["survival_runway_days"]

        state["risk"] = risk
        return state
