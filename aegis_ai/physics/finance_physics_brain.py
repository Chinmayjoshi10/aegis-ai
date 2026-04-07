import numpy as np
import pandas as pd

class FinancePhysicsBrain:
    """
    Finance is modeled as a CASH FLOW / BURN / RESERVE PRESSURE system.

    Inputs  : state["features"]["finance"]
    Outputs : state["physics"]["finance"]
    """

    def run(self, state: dict):
        df = state["features"].get("finance")
        if df is None or len(df) < 5:
            state["physics"]["finance"] = {"status": "INSUFFICIENT_DATA"}
            return state

        # -----------------------------
        # PHYSICAL VARIABLES
        # -----------------------------

        # Income Flow
        income = df["daily_revenue"].rolling(7).mean().iloc[-1]

        # Burn Rate
        burn = df["daily_expenses"].rolling(7).mean().iloc[-1]

        # Net Metabolic Rate
        net = income - burn

        # Reserve Pressure
        cash_reserve = df["cash_reserve"].iloc[-1]

        # Survival Runway (days)
        runway = cash_reserve / max(abs(net), 1)

        # Fragility (financial instability)
        fragility = burn / max(income, 1)

        # Failure Probability
        failure_prob = min(1.0, fragility / 2)

        state["physics"]["finance"] = {
            "income_flow": round(income, 2),
            "burn_rate": round(burn, 2),
            "net_flow": round(net, 2),
            "cash_reserve": round(cash_reserve, 2),
            "fragility": round(fragility, 3),
            "survival_runway_days": round(runway, 1),
            "failure_probability": round(failure_prob, 3),
            "status": "OK"
        }

        return state
