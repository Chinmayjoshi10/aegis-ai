import numpy as np
import pandas as pd

class OpsPhysicsBrain:
    """
    Operations is modeled as a LOAD / STRAIN / FATIGUE physical system.

    Inputs  : state["features"]["ops"]
    Outputs : state["physics"]["ops"]
    """

    def run(self, state: dict):
        df = state["features"].get("ops")
        if df is None or len(df) < 5:
            state["physics"]["ops"] = {"status": "INSUFFICIENT_DATA"}
            return state

        # -----------------------------
        # PHYSICAL VARIABLES
        # -----------------------------

        # Load (work inflow)
        load = df["tasks_inflow"].rolling(7).mean().iloc[-1]

        # Throughput (work processed)
        throughput = df["tasks_completed"].rolling(7).mean().iloc[-1]

        # Strain (load vs capacity)
        strain = load / max(throughput, 1)

        # Backlog Pressure
        backlog_pressure = df["backlog_size"].iloc[-1]

        # Fatigue (chronic overload)
        fatigue = strain * backlog_pressure

        # Survival Runway (days before ops collapse)
        runway = backlog_pressure / max(throughput - load, 1)

        # Failure Probability
        failure_prob = min(1.0, fatigue / 1000)

        state["physics"]["ops"] = {
            "load": round(load, 2),
            "throughput": round(throughput, 2),
            "strain": round(strain, 3),
            "backlog_pressure": int(backlog_pressure),
            "fatigue": round(fatigue, 2),
            "survival_runway_days": round(runway, 1),
            "failure_probability": round(failure_prob, 3),
            "status": "OK"
        }

        return state
