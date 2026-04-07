import pandas as pd

class FinanceComplianceAdapter:
    """
    Converts finance / accounting data into Aegis compliance intelligence.
    """

    def adapt(self, df: pd.DataFrame) -> pd.DataFrame:
        mapping = {}

        if "invoice_amount" in df.columns:
            mapping["billing_load"] = df["invoice_amount"]

        if "tax_rate" in df.columns:
            mapping["tax_pressure"] = df["tax_rate"]

        if "payment_delay_days" in df.columns:
            mapping["payment_risk"] = df["payment_delay_days"]

        result = pd.DataFrame(mapping)

        # If the adapter rules didn't match, fallback to numeric columns and sanitize
        if result.empty:
            df = df.copy()
            for col in list(df.columns):
                if df[col].dtype == "object":
                    try:
                        df[col] = pd.to_numeric(df[col])
                    except Exception:
                        df = df.drop(columns=[col])

            for col in list(df.columns):
                if df[col].nunique() <= 1:
                    df = df.drop(columns=[col])

            return df

        return result
