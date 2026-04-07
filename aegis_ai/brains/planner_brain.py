class PlannerBrain:
    """
    Generates what-if action plans.
    """

    def plan(self, risk_state: dict):
        plans = {
            "CRITICAL": ["Shutdown", "Notify Safety", "Inspect Equipment"],
            "HIGH": ["Reduce Load", "Increase Monitoring"],
            "ELEVATED": ["Schedule Inspection"],
            "NORMAL": ["No Action"]
        }
        state = risk_state.get("risk_state")
        # Validate key is a string before using it as a dict key to satisfy static checkers
        if not isinstance(state, str):
            return ["Review"]
        return plans.get(state, ["Review"])
