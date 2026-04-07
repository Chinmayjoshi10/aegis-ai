import numpy as np
import pandas as pd

class LogisticsPhysicsBrain:
    """
    Logistics is modeled as a FLOW / FRICTION / BLOCKAGE physical system.

    Inputs  : state["features"]["logistics"]
    Outputs : state["physics"]["logistics"]
    """

    def run(self, state: dict):
        df = state["features"].get("logistics")
        if df is None or len(df) < 5:
            state["physics"]["logistics"] = {"status": "INSUFFICIENT_DATA"}
            return state

        # -----------------------------
        # PHYSICAL VARIABLES
        # -----------------------------

        # Flow Rate (shipments/day)
        flow_rate = df["shipments_sent"].rolling(7).mean().iloc[-1]

        # Delay (mean delivery delay days)
        delay = df["avg_delivery_delay_days"].rolling(7).mean().iloc[-1]

        # Blockage (stuck shipments)
        blockage = df["shipments_delayed"].rolling(7).mean().iloc[-1]

        # Friction (resistance)
        friction = delay * blockage

        # Backpressure (inventory at risk)
        backpressure = df["inventory_backlog"].iloc[-1]

        # Survival Runway
        runway = backpressure / max(flow_rate - blockage, 1)

        # Failure Probability
        failure_prob = min(1.0, friction / 100)

        state["physics"]["logistics"] = {
            "flow_rate": round(flow_rate, 2),
            "delay": round(delay, 2),
            "blockage": round(blockage, 2),
            "friction": round(friction, 2),
            "backpressure": int(backpressure),
            "survival_runway_days": round(runway, 1),
            "failure_probability": round(failure_prob, 3),
            "status": "OK"
        }

        return state
