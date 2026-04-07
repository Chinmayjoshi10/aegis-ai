import numpy as np
import pandas as pd

class OutputNormalizerAgent:
    """
    Converts numpy / pandas types to pure Python types for API safety.
    """

    def normalize(self, obj):
        # dicts and lists: recurse
        if isinstance(obj, dict):
            return {k: self.normalize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.normalize(v) for v in obj]

        # pandas DataFrame / Series
        elif isinstance(obj, pd.DataFrame):
            # convert to list of records and normalize each value
            records = obj.to_dict(orient='records')
            return [self.normalize(r) for r in records]
        elif isinstance(obj, pd.Series):
            return [self.normalize(v) for v in obj.tolist()]

        # numpy scalar and arrays
        elif isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        elif isinstance(obj, np.ndarray):
            return [self.normalize(v) for v in obj.tolist()]

        # pandas timestamps and missing values
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif pd.isna(obj):
            return None

        # fallback
        else:
            return obj

    def run(self, state: dict):
        state.setdefault("intelligence", {})

        normalized_intelligence = self.normalize(state["intelligence"])
        decision_packet = dict(normalized_intelligence)

        state["intelligence"] = normalized_intelligence
        state["intelligence"]["decision_packet"] = decision_packet
        return state
