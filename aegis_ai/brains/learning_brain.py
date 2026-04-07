import pandas as pd
from sklearn.ensemble import IsolationForest

class LearningBrain:
    """
    Learns baseline behavior and detects early drift.
    """

    def __init__(self):
        self.model = IsolationForest(contamination=0.05)

    def train(self, df):
        self.model.fit(df)

    def predict_drift(self, df):
        preds = self.model.predict(df)
        return (preds == -1).mean()  # drift ratio
