import pandas as pd

class DataIntegrityAgent:
    """
    Cleans, normalizes and audits data quality before intelligence processing.
    Acts as a safety gate for the entire Decision OS.
    """

    def run(self, state: dict):
        df = state["data"]

        # 🚨 Hard safety gate
        if df is None or df.empty:
            state["halt_pipeline"] = True
            state["error"] = "EMPTY_OR_INVALID_DATA"
            return state

        report = {}

        for col in df.columns:
            missing_ratio = float(df[col].isna().mean())
            report[col] = round(missing_ratio, 3)

            # Modern Pandas-safe filling
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].ffill().bfill()
                df[col] = df[col].fillna(df[col].median())
            else:
                df[col] = df[col].ffill().bfill()
                df[col] = df[col].fillna("UNKNOWN")

        state["data"] = df
        state["data_quality"] = report
        return state
