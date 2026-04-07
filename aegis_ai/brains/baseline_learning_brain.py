import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from aegis_ai.memory.baseline_model_store import BaselineModelStore

class BaselineLearningBrain:
    """
    Drift-aware baseline envelope learner.
    """

    def __init__(self):
        self.model = None

    def train(self, df: pd.DataFrame):
        numeric = df.select_dtypes(include="number")
        if numeric.empty:
            return None

        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("model", IsolationForest(contamination=0.05))
        ])

        pipe.fit(numeric)
        self.model = pipe
        return pipe

    def persist(self, tenant: str):
        if self.model is None:
            return None
        store = BaselineModelStore()
        store.save(tenant, self.model)
        return True

    def score(self, model, df: pd.DataFrame):
        numeric = df.select_dtypes(include="number")
        if numeric.empty:
            return None
        return float(model.named_steps["model"].decision_function(
            model.named_steps["scaler"].transform(numeric)
        ).mean())
