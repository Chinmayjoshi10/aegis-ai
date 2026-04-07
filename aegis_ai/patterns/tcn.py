from typing import List
import time

import numpy as np
import pandas as pd

from aegis_ai.patterns.signals import PatternSignal


class TCNSequenceAnomalyDetector:
    """
    Single-metric TCN autoencoder with:
    - lazy torch import
    - hard time budget (per request)
    - fail-open behavior
    """

    def __init__(
        self,
        window_size: int = 30,
        min_history: int = 90,
        epochs: int = 3,
        threshold: float = 3.0,
        max_seconds: int = 5,   # ⏱ HARD TIME BUDGET
    ):
        self.window_size = window_size
        self.min_history = min_history
        self.epochs = epochs
        self.threshold = threshold
        self.max_seconds = max_seconds

    def detect(
        self,
        df: pd.DataFrame,
        tenant_id: str,
        domain: str,
        state: dict,
    ) -> List[PatternSignal]:

        start_time = time.time()

        # -----------------------------
        # Lazy torch import
        # -----------------------------
        try:
            import torch
            import torch.nn as nn
            import torch.optim as optim
        except Exception:
            return []

        signals: List[PatternSignal] = []
        clock = state["_clock"]

        numeric_cols = df.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:

            # ⏱ TIME BUDGET CHECK
            if time.time() - start_time > self.max_seconds:
                break

            series = df[col].dropna().values.astype(np.float32)
            if len(series) < self.min_history:
                continue

            windows = np.array(
                [
                    series[i : i + self.window_size]
                    for i in range(len(series) - self.window_size)
                ]
            )

            if len(windows) < 10:
                continue

            x_train = torch.tensor(windows).unsqueeze(1)

            model = nn.Sequential(
                nn.Conv1d(1, 16, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.Conv1d(16, 1, kernel_size=3, padding=1),
            )

            optimizer = optim.Adam(model.parameters(), lr=1e-3)
            loss_fn = nn.MSELoss()

            # -----------------------------
            # Train
            # -----------------------------
            for _ in range(self.epochs):
                optimizer.zero_grad()
                recon = model(x_train)
                loss = loss_fn(recon, x_train)
                loss.backward()
                optimizer.step()

            # -----------------------------
            # Reconstruction error
            # -----------------------------
            with torch.no_grad():
                recon_train = model(x_train)
                train_err = ((recon_train - x_train) ** 2).mean(dim=(1, 2)).numpy()

            mean_err = train_err.mean()
            std_err = train_err.std() + 1e-6

            last_window = series[-self.window_size :]
            x_last = torch.tensor(last_window).unsqueeze(0).unsqueeze(0)

            with torch.no_grad():
                recon_last = model(x_last)
                last_err = ((recon_last - x_last) ** 2).mean().item()

            z = (last_err - mean_err) / std_err

            if z >= self.threshold:
                signals.append(
                    PatternSignal(
                        tenant_id=tenant_id,
                        domain=domain,
                        metric=col,
                        signal_type="SEQUENCE_ANOMALY",
                        strength=min(z / 6.0, 1.0),
                        confidence="MEDIUM",
                        window=f"last_{self.window_size}_points",
                        detected_at=clock.now(),
                        model="tcn",
                        version="v1",
                    )
                )

        return signals
