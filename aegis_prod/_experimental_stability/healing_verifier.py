class HealingVerifier:
    """
    Verifies improvement and triggers Phase Lock after 2 consecutive NO_IMPROVEMENT cycles.
    """

    def __init__(self):
        self.prev_risk = None
        self.no_improve_streak = 0

    def run(self, state: dict):
        cur = state.get("physics", {}).get("global_collapse_risk")
        if cur is None:
            return state

        if self.prev_risk is not None:
            delta = self.prev_risk - cur
            if delta > 0:
                self.no_improve_streak = 0
                state["healing_effect"] = "IMPROVING"
            else:
                self.no_improve_streak += 1
                state["healing_effect"] = "NO_IMPROVEMENT"

                # Phase Lock after 2 consecutive failures
                if self.no_improve_streak >= 2:
                    # Engage Phase Lock
                    ctrl = state.get("_homeostasis_controller")
                    if ctrl:
                        ctrl.phase_locked = True
                    state["phase_lock"] = True
                    state["escalation"] = {
                        "level": "HUMAN_REQUIRED",
                        "reason": "PERSISTENT_NO_IMPROVEMENT"
                    }

        self.prev_risk = cur
        return state
