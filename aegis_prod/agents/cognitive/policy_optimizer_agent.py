from aegis_ai.brains.policy_optimizer_brain import PolicyOptimizerBrain
from aegis_ai.brains.drift_explanation_brain import DriftExplanationBrain

class PolicyOptimizerAgent:
    """
    Cybernetic pivot:
    - Generates learning feedback
    - Performs causal drift reasoning
    - Emits self-healing remediation patches
    """

    def __init__(self):
        self.brain = PolicyOptimizerBrain()
        self.drift_brain = DriftExplanationBrain()   # ← REAL v3 drift intelligence

    def run(self, state: dict):
        tenant = state["domain"]
        risk = state.get("risk", {}).get("risk_state", "NORMAL")

        # 1. Normal policy optimization (unchanged)
        history = state.get("history", [])
        recommendation = self.brain.optimize(history)
        state["policy_recommendation"] = recommendation

        # 2. Causal drift introspection (REAL v3 logic)
        drift_report = self.drift_brain.explain(state)
        state["drift_report"] = drift_report

        # 3. Escalation decision based on predicted future drift
        fdr = state.get("future_drift_risk", 0.0)
        if fdr and fdr > 0.2:
            state["escalation"] = {"level": "ESCALATE", "reason": "predicted_drift", "risk": float(fdr)}
        else:
            state["escalation"] = None

        # 4. Cybernetic feedback to learning core
        state["learning_feedback"] = {
            "adjust_contamination": 0.03 if risk == "CRITICAL" else 0.05
        }

        return state
