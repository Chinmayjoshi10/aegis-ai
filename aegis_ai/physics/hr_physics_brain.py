import numpy as np
import pandas as pd

class HRPhysicsBrain:
    """
    HR is modeled as a CAPACITY / BURNOUT / ATTRITION PRESSURE system.

    Inputs  : state["features"]["hr"]
    Outputs : state["physics"]["hr"]
    """

    def run(self, state: dict):
        df = state["features"].get("hr")
        if df is None or len(df) < 5:
            state["physics"]["hr"] = {"status": "INSUFFICIENT_DATA"}
            return state

        # -----------------------------
        # PHYSICAL VARIABLES
        # -----------------------------

        # Workforce Capacity
        capacity = df["active_employees"].iloc[-1]

        # Workload Pressure
        workload = df["avg_tasks_per_employee"].rolling(7).mean().iloc[-1]

        # Attrition Rate
        attrition = df["attrition_rate"].rolling(7).mean().iloc[-1]

        # Burnout Pressure
        burnout = workload * attrition

        # Hiring Velocity
        hiring_rate = df["new_hires"].rolling(7).mean().iloc[-1]

        # Survival Runway
        runway = capacity / max(attrition * capacity - hiring_rate, 1)

        # Failure Probability
        failure_prob = min(1.0, burnout / 10)

        state["physics"]["hr"] = {
            "capacity": int(capacity),
            "workload": round(workload, 2),
            "attrition_rate": round(attrition, 3),
            "burnout_pressure": round(burnout, 2),
            "hiring_velocity": round(hiring_rate, 2),
            "survival_runway_days": round(runway, 1),
            "failure_probability": round(failure_prob, 3),
            "status": "OK"
        }

        return state
