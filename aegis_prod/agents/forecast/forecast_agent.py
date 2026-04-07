import numpy as np


class ForecastAgent:
    """Runs ForecastBrainV4 when possible; falls back to a simple naive forecast
    when data is insufficient or the model cannot run (useful for tests).
    """

    def run(self, state: dict):
        tenant = state.get("tenant") or state.get("domain")
        df = state.get("data")

        ent = {}
        # Import model lazily to avoid hard dependency at import-time
        try:
            from aegis_ai.memory.forecast_brain import ForecastBrainV4
            fb = ForecastBrainV4(tenant)
            result = fb.run()
            ent = result.get("enterprise_forecast") if result else {}
        except Exception:
            ent = {}

        # If model produced nothing, create a naive fallback forecast
        if not ent and df is not None:
            ent = {}
            numeric = df.select_dtypes(include="number").columns
            for c in numeric:
                last = float(df[c].iloc[-1])
                ent[c] = [[last * 0.9], [last], [last * 1.1]]

        state["forecast"] = {"enterprise_forecast": ent}

        state.setdefault("intelligence", {})
        state["intelligence"]["forecast"] = state["forecast"]
        return state
