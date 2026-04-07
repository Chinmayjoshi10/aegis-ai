import numpy as np
import pandas as pd

class SalesPhysicsBrain:
    """
    Sales is modeled as a PRESSURIZED FLOW SYSTEM.

    Inputs  : state["features"]["sales"]
    Outputs : state["physics"]["sales"]

    This becomes the ONLY sales truth layer.
    """

    def run(self, state: dict):
        df = state["features"].get("sales")
        if df is None or len(df) < 5:
            state["physics"]["sales"] = {"status": "INSUFFICIENT_DATA"}
            return state

        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df = df.dropna(subset=["created_at"])

        # -----------------------------
        # PHYSICAL VARIABLES
        # -----------------------------

        # Flow Rate (leads / day)
        daily_flow = df.groupby(df["created_at"].dt.date).size()
        flow_rate = daily_flow.rolling(7).mean().iloc[-1]

        # Pressure (open pipeline value)
        open_pipe = df[df["stage"] != "CLOSED_WON"]
        pressure = open_pipe["lead_value"].sum()

        # Leakage (lost / stalled)
        stalled = df[df["stage"] == "LOST"]
        leakage_rate = len(stalled) / max(len(df), 1)

        # Impedance (sales friction)
        impedance = 1 / max(flow_rate, 0.1)

        # Fragility (structural instability)
        fragility = leakage_rate * impedance

        # Survival Runway (days to collapse)
        runway = pressure / max(flow_rate * (1 - leakage_rate), 1)

        # Failure Probability (physical collapse likelihood)
        failure_prob = min(1.0, fragility * 1.4)

        state["physics"]["sales"] = {
            "flow_rate": round(flow_rate, 3),
            "pressure": round(pressure, 2),
            "leakage_rate": round(leakage_rate, 3),
            "impedance": round(impedance, 3),
            "fragility": round(fragility, 3),
            "survival_runway_days": round(runway, 1),
            "failure_probability": round(failure_prob, 3),
            "status": "OK"
        }

        return state
