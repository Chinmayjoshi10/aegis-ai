import os
import pandas as pd
from datetime import datetime

class ShadowBaselineStore:
    """
    Immutable raw-reality memory.
    """

    BASE = "shadow_memory/"

    def persist(self, tenant_id: str, raw_df: pd.DataFrame):
        os.makedirs(self.BASE + tenant_id, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        pq_path = f"{self.BASE}{tenant_id}/{ts}.parquet"
        csv_path = f"{self.BASE}{tenant_id}/{ts}.csv"
        try:
            # Prefer parquet when available
            raw_df.to_parquet(pq_path)
        except Exception:
            # Fallback to CSV when parquet engines are not installed
            raw_df.to_csv(csv_path, index=False)

    def load(self, tenant_id: str) -> pd.DataFrame:
        folder = self.BASE + tenant_id
        if not os.path.exists(folder):
            return pd.DataFrame()
        files = sorted(os.listdir(folder))
        dfs = []
        for f in files[-5:]:
            path = os.path.join(folder, f)
            if f.endswith(".parquet"):
                try:
                    dfs.append(pd.read_parquet(path))
                except Exception:
                    continue
            elif f.endswith(".csv"):
                try:
                    dfs.append(pd.read_csv(path))
                except Exception:
                    continue
        if not dfs:
            return pd.DataFrame()
        return pd.concat(dfs, ignore_index=True)

    def load_xy(self, tenant_id: str):
        df = self.load(tenant_id)
        if df.empty:
            return pd.DataFrame(), pd.Series(dtype=float)
        y = df["target"] if "target" in df.columns else pd.Series(dtype=float)
        X = df.drop(columns=["target"]) if "target" in df.columns else df
        return X, y
