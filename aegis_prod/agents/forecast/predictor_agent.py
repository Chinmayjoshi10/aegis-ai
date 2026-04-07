from aegis_ai.brains.learning_brain import LearningBrain


class PredictorAgent:
    """
    Predicts future drift risk.
    """

    def __init__(self):
        self.brain = LearningBrain()
        self.trained = False

    def run(self, state: dict):
        df = state["data"]

        if not self.trained:
            self.brain.train(df)
            self.trained = True

        drift_risk = self.brain.predict_drift(df)
        state["future_drift_risk"] = round(float(drift_risk), 3)
        return state
