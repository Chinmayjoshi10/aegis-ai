from aegis_ai.brains.planner_brain import PlannerBrain

class PlannerAgent:
    def __init__(self):
        self.brain = PlannerBrain()

    def run(self, state: dict):
        state["plans"] = self.brain.plan(state["risk"])
        return state
