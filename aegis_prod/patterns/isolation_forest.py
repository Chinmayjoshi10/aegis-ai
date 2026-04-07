from typing import List

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from aegis_ai.patterns.signals import PatternSignal


class IsolationForestDetector:
    """
    Point-anomaly detector using Isolation Forest.

    Design goals:
    - Unsupervised
    - Conservative (low false positives)
    - Cold-start safe
    - Ignores non-business / index columns
    """

    def __init__(
        self,
        contamination: float = 0.05,
        min_history: int = 30,
        random_state: int = 42,
    ):
        self.contamination = contamination
        self.min_history = min_history
        self.random_state = random_state

    def detect(
        self,
        df: pd.DataFrame,
        tenant_id: str,
        domain: str,
        state: dict,
    ) -> List[PatternSignal]:

        signals: List[PatternSignal] = []
        clock = state["_clock"]

        # --- Select numeric, semantic columns only ---
        numeric_cols = [
            c
            for c in df.select_dtypes(include=[np.number]).columns
            if not c.lower().startswith("unnamed")
        ]

        for col in numeric_cols:
            series = df[col].dropna()

            # --- Cold start guard ---
            if len(series) < self.min_history:
                continue

            values = series.values.reshape(-1, 1)

            model = IsolationForest(
                contamination=self.contamination,
                random_state=self.random_state,
            )
            model.fit(values)

            scores = model.decision_function(values)
            preds = model.predict(values)  # -1 = anomaly, 1 = normal

            # --- Only evaluate the most recent point ---
            if preds[-1] == -1:
                strength = min(abs(scores[-1]), 1.0)

                signal = PatternSignal(
                    tenant_id=tenant_id,
                    domain=domain,
                    metric=col,
                    signal_type="POINT_ANOMALY",
                    strength=float(round(strength, 3)),
                    confidence="MEDIUM",  # confidence logic comes later
                    window="latest_point",
                    detected_at=clock.now(),
                    model="isolation_forest",
                    version="v1",
                )

                signals.append(signal)

        return signals
