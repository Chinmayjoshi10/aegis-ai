from aegis_ai.brains.baseline_learning_brain import BaselineLearningBrain

from aegis_ai.memory.shadow_baseline_store import ShadowBaselineStore


class LearningAgent:
    """
    Shadow-enforced baseline learner.
    Baselines are ALWAYS trained on raw (shadow) reality.
    Never on cleaned / filtered / remediated data.
    """

    def __init__(self):
        self.brain = BaselineLearningBrain()
        self.shadow = ShadowBaselineStore()

    def run(self, state: dict):
        tenant = state["domain"]

        # Load immutable raw truth
        X, y = self.shadow.load_xy(tenant)

        # Train / update baseline envelopes
        self.brain.train(X)

        # Persist trained model (your existing model store logic)
        self.brain.persist(tenant)

        # No mutation of state data
        state["baseline_trained"] = True
        return state
