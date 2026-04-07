import re
import numpy as np
import pandas as pd

class DataSanitizer:
    """
    Smarter enterprise sanitizer:
    - Cleans numeric columns
    - Preserves IDs and categories
    - Parses dates correctly
    """

    NUMERIC_HINTS = [
        "price",
        "amount",
        "qty",
        "quantity",
        "total",
        "revenue",
        "cost",
        "value",
        "sales"
    ]

    CATEGORICAL_HINTS = [
        "gender",
        "category",
        "product",
        "region",
        "channel",
        "store",
        "brand"
    ]

    ID_HINTS = [
        "id",
        "customer",
        "transaction",
        "order",
        "invoice"
    ]

    def _clean_numeric(self, x):
        if pd.isna(x):
            return np.nan

        if isinstance(x, (int, float, np.integer, np.floating)):
            return float(x)

        s = str(x).strip()

        if s == "":
            return np.nan

        s = re.sub(r"[$₹€£]", "", s)
        s = s.replace(",", "")

        if "%" in s:
            try:
                return float(s.replace("%", "")) / 100.0
            except Exception:
                return np.nan

        try:
            return float(s)
        except Exception:
            return np.nan

    def should_be_numeric(self, col: str) -> bool:
        lc = col.lower()
        return any(h in lc for h in self.NUMERIC_HINTS)

    def should_be_categorical(self, col: str) -> bool:
        lc = col.lower()
        return any(h in lc for h in self.CATEGORICAL_HINTS)

    def should_be_id(self, col: str) -> bool:
        lc = col.lower()
        return any(h in lc for h in self.ID_HINTS)

    def sanitize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        for col in df.columns:
            lc = col.lower()

            # 1) Parse dates properly
            if "date" in lc:
                df[col] = pd.to_datetime(df[col], errors="coerce")
                continue

            # 2) Preserve IDs as strings
            if self.should_be_id(col):
                df[col] = df[col].astype(str)
                continue

            # 3) Preserve categorical columns
            if self.should_be_categorical(col):
                df[col] = df[col].astype(str)
                continue

            # 4) Clean only true numeric columns
            if self.should_be_numeric(col):
                df[col] = df[col].apply(self._clean_numeric)

        return df
