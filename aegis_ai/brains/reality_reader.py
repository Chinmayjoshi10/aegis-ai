import pandas as pd
import numpy as np
import re
 
 
class RealityReader:
    """
    INDUSTRIAL-GRADE OBSERVER
 
    What this version does:
    - Rescues numeric meaning from messy object columns
    - Computes health ratios (null, zero)
    - Counts 3-sigma outliers
    - Performs metabolic consistency checks
    - Profiles key categorical columns for later drift detection
    - ADDS OPERATING REGIME CONTEXT (NON-BREAKING)
 
    HARD RULE:
    - NEVER throws
    - NEVER blocks the pipeline
    """
 
    # -------------------------------------------------------
    # 1) Messy numeric coercion (FAIL-OPEN)
    # -------------------------------------------------------
 
    def _coerce_messy_numeric(self, series: pd.Series) -> pd.Series:
        def clean_val(x):
            if isinstance(x, (list, tuple, dict, set, np.ndarray, pd.Series)):
                return np.nan
            if x is None:
                return np.nan
 
            if isinstance(x, (int, float, np.integer, np.floating)):
                return float(x)
 
            try:
                s = str(x).strip()
            except Exception:
                return np.nan
 
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
 
        return series.apply(clean_val)
 
    # -------------------------------------------------------
    # 2) Core profile method
    # -------------------------------------------------------
 
    def profile(self, df: pd.DataFrame) -> dict:
        stats = {}
        issues = []
        categorical_health = {}
 
        # ---------------------------------------------------
        # Identify numeric columns (including messy objects)
        # ---------------------------------------------------
        from aegis_ai.sanitizer.column_filter import is_metric_column
 
        numeric_columns = []
 
        for col in df.columns:
            try:
                if pd.api.types.is_numeric_dtype(df[col]):
                    is_metric, _ = is_metric_column(col, df[col])
                    if is_metric:
                        numeric_columns.append(col)
                else:
                    coerced = self._coerce_messy_numeric(df[col])
                    if coerced.notna().sum() > 0:
                        is_metric, _ = is_metric_column(col, coerced)
                        if is_metric:
                            df[col] = coerced
                            numeric_columns.append(col)
            except Exception:
                continue
 
        # ---------------------------------------------------
        # 3) Metabolic Consistency Check
        # ---------------------------------------------------
        if {"Quantity", "Price_per_Unit", "Total_Amount"}.issubset(df.columns):
            try:
                mismatch_mask = (
                    (df["Quantity"] * df["Price_per_Unit"] - df["Total_Amount"])
                    .abs() > 1e-6
                )
 
                mismatches = int(mismatch_mask.sum())
 
                if mismatches > 0:
                    issues.append({
                        "type": "METABOLIC_BROKEN",
                        "mismatch_rows": mismatches,
                        "suggested_fix":
                            "Recompute Total_Amount = Quantity * Price_per_Unit",
                        "confidence": 0.92
                    })
            except Exception:
                pass
 
        # ---------------------------------------------------
        # 4) Numeric health statistics
        # ---------------------------------------------------
        for c in numeric_columns:
            try:
                s = df[c].dropna()
                if len(s) == 0:
                    continue
 
                mean = float(s.mean())
                std = float(s.std(ddof=0))
                median = float(s.median())
                minv = float(s.min())
                maxv = float(s.max())
 
                null_ratio = float(df[c].isna().mean())
                zero_ratio = float((df[c] == 0).mean())
 
                if std > 0:
                    three_sigma_outliers = int(
                        ((s - mean).abs() > 3 * std).sum()
                    )
                else:
                    three_sigma_outliers = 0
 
                stats[c] = {
                    "mean": mean,
                    "median": median,
                    "std": std,
                    "min": minv,
                    "max": maxv,
                    "count": int(len(s)),
                    "null_ratio": round(null_ratio, 4),
                    "zero_ratio": round(zero_ratio, 4),
                    "three_sigma_outliers": three_sigma_outliers,
                }
            except Exception:
                continue
 
        # ---------------------------------------------------
        # 5) Categorical Health
        # ---------------------------------------------------
        if "Product_Category" in df.columns:
            try:
                cats = df["Product_Category"].dropna().value_counts()
                categorical_health["Product_Category"] = {
                    "unique_count": int(cats.nunique()),
                    "top_categories": cats.head(5).to_dict(),
                    "rare_categories": cats[cats < 5].index.tolist(),
                }
            except Exception:
                pass
 
        # ---------------------------------------------------
        # 6) REGIME SEGMENTATION (SAFE, ADDITIVE)
        # ---------------------------------------------------
        regime = self._derive_regime(df, stats)
 
        # ---------------------------------------------------
        # Final report (SOURCE OF TRUTH)
        # ---------------------------------------------------
        return {
            "numeric_columns": numeric_columns,
            "stats": stats,
            "issues": issues,
            "categorical_health": categorical_health,
            "regime": regime,   # ✅ NEW, NON-BREAKING FIELD
        }
 
    # -------------------------------------------------------
    # 7) Deterministic Regime Derivation (FAIL-OPEN)
    # -------------------------------------------------------
 
    def _derive_regime(self, df: pd.DataFrame, stats: dict) -> dict:
        """
        Context-only regime classification.
 
        - No ML
        - No insights
        - Fail-open
        """
 
        # -------------------------
        # LOAD (volume proxy)
        # -------------------------
        try:
            row_count = len(df)
            if row_count < 1_000:
                load = "LOW"
            elif row_count > 100_000:
                load = "HIGH"
            else:
                load = "NORMAL"
        except Exception:
            load = "NORMAL"
 
        # -------------------------
        # STRESS (internal strain)
        # -------------------------
        stress_flags = 0
 
        try:
            stds = [
                v["std"] for v in stats.values()
                if isinstance(v, dict) and "std" in v
            ]
            means = [
                abs(v["mean"]) for v in stats.values()
                if isinstance(v, dict) and "mean" in v
            ]
 
            if stds and means:
                avg_std = np.mean(stds)
                avg_mean = np.mean(means)
                if avg_mean > 0 and (avg_std / avg_mean) > 1.5:
                    stress_flags += 1
        except Exception:
            pass
 
        try:
            total_outliers = sum(
                v.get("three_sigma_outliers", 0)
                for v in stats.values()
                if isinstance(v, dict)
            )
            if len(df) > 0 and (total_outliers / len(df)) > 0.08:
                stress_flags += 1
        except Exception:
            pass
 
        try:
            avg_null_ratio = np.mean([
                v.get("null_ratio", 0)
                for v in stats.values()
                if isinstance(v, dict)
            ])
            if avg_null_ratio > 0.1:
                stress_flags += 1
        except Exception:
            pass
 
        stress = "STRESSED" if stress_flags >= 2 else "NORMAL"
 
        return {
            "load": load,
            "stress": stress,
        }
 