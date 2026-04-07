import pandas as pd

class ManufacturingAdapter:
    """
    Sanitizes any industrial manufacturing CSV into numeric-safe channels.
    """

    def adapt(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # Drop obvious non-signal columns
        for col in list(df.columns):
            if df[col].dtype == "object":
                try:
                    df[col] = pd.to_numeric(df[col])
                except:
                    df = df.drop(columns=[col])

        # Remove constant columns
        for col in list(df.columns):
            if df[col].nunique() <= 1:
                df = df.drop(columns=[col])

        return df
