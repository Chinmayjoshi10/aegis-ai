class FeatureBrain:
    """
    Canonical enterprise skeleton generator.
    Guarantees that every physics organ and artery exists before coupling begins.
    This permanently prevents all KeyError propagation.
    """

    def run(self, state: dict):

        state.setdefault("physics", {})
        P = state["physics"]

        BASE = {
            "sales": {
                "flow_rate": 0,
                "leakage_rate": 0,
                "failure_probability": 0.05
            },
            "ops": {
                "throughput": 0,
                "fatigue": 0,
                "failure_probability": 0.10
            },
            "logistics": {
                "blockage": 0,
                "flow_rate": 0,
                "failure_probability": 0.08
            },
            "finance": {
                "burn_rate": 0,
                "cash_reserve": 0,
                "fragility": 0.20
            },
            "hr": {
                "burnout_pressure": 0,
                "attrition_rate": 0,
                "failure_probability": 0.05
            }
        }

        # Hard-patch all missing arteries
        for organ, arteries in BASE.items():
            P.setdefault(organ, {})
            for artery, baseline in arteries.items():
                P[organ].setdefault(artery, baseline)

        return state
