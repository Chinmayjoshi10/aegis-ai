from aegis_ai.core.agent_base import Agent
from aegis_ai.brains.feature_brain import FeatureBrain


class FeatureBrainAgent(Agent):
    def __init__(self):
        super().__init__("FeatureBrain")
        self.brain = FeatureBrain()

    def run(self, state: dict):
        df = state.get("data")
        if df is None:
            return

        # Learn baseline only once
        if not self.brain.baselines:
            self.brain.learn_baseline(df)

        features = self.brain.extract(df)

        # 🧠 EMIT FEATURES INTO CORTEX
        state.setdefault("intelligence", {})
        state["intelligence"]["features"] = features

        # Legacy compatibility
        state["features"] = features
