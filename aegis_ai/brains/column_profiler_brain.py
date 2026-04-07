import pandas as pd
import numpy as np
import re

class ColumnProfilerBrain:
    """
    Produces deep semantic fingerprints for unknown columns.
    Optimized and temporal-aware.
    """

    EMAIL_RE = re.compile(r"[^@]+@[^@]+\.[^@]+")
    UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")

    def _looks_temporal(self, s: pd.Series) -> bool:
        # Try coercing a sample to datetime; if most parse, it's temporal
        sample = s.sample(min(50, len(s)))
        parsed = self._coerce_sample_to_datetime(sample)
        return parsed.notna().mean() > 0.7  # 70%+ parse success → temporal

    def _coerce_sample_to_datetime(self, sample: pd.Series) -> pd.Series:
        """Try to coerce a sample of strings to datetimes with minimal warnings.

        Strategy:
        - Check for a dominant simple format (YYYY-MM-DD, DD-MM-YYYY, etc.) and apply a
          `format=` to `pd.to_datetime` for speed and no warnings when possible.
        - If no dominant format is found, fall back to `pd.to_datetime` but suppress the
          "Could not infer format" UserWarning which pandas emits during element-wise parsing.
        """
        import warnings

        s = sample.dropna().astype(str)
        if s.empty:
            return pd.Series([], dtype='datetime64[ns]')

        # Candidate format patterns (regex, pandas format string)
        candidates = [
            (r"^\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
            (r"^\d{2}-\d{2}-\d{4}", "%d-%m-%Y"),
            (r"^\d{4}/\d{2}/\d{2}", "%Y/%m/%d"),
            (r"^\d{2}/\d{2}/\d{4}", "%d/%m/%Y"),
        ]

        for pattern, fmt in candidates:
            matches = s.str.match(pattern).sum()
            if matches / len(s) > 0.6:
                # If times appear, try with time portion; try common time patterns
                if s.str.contains(":").any():
                    # Try with seconds, then without
                    for time_suffix in (" %H:%M:%S", " %H:%M"):
                        try_fmt = fmt + time_suffix
                        try:
                            parsed = pd.to_datetime(s, format=try_fmt, errors="coerce", utc=True)
                            if parsed.notna().any():
                                return parsed
                        except Exception:
                            continue
                else:
                    try:
                        parsed = pd.to_datetime(s, format=fmt, errors="coerce", utc=True)
                        if parsed.notna().any():
                            return parsed
                    except Exception:
                        continue

        # Fallback: use pandas parsing but suppress the "Could not infer format" warning
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Could not infer format",
            )
            parsed = pd.to_datetime(s, errors="coerce", utc=True, dayfirst=True)
        return parsed

    def profile(self, df: pd.DataFrame):
        profiles = {}

        n_rows = len(df)

        for col in df.columns:
            s = df[col].dropna()
            if s.empty:
                continue

            is_numeric = pd.api.types.is_numeric_dtype(s)
            unique_count = int(s.nunique())
            unique_ratio = unique_count / len(s)
            null_ratio = 1 - (len(s) / n_rows)

            # Prepare samples once (avoid repeated astype in loops)
            sample = s.sample(min(50, len(s)))

            profile = {
                "dtype": str(s.dtype),
                "null_ratio": null_ratio,
                "unique_count": unique_count,
                "unique_ratio": unique_ratio,
                "sample_values": sample.head(5).astype(str).tolist()
            }

            # Temporal detection (even if object dtype)
            is_temporal = False
            if not is_numeric:
                try:
                    is_temporal = self._looks_temporal(s)
                except Exception:
                    is_temporal = False

            if is_numeric:
                profile.update({
                    "semantic_hint": "numeric",
                    "min": float(s.min()),
                    "max": float(s.max()),
                    "mean": float(s.mean()),
                    "std": float(s.std())
                })
            elif is_temporal:
                profile.update({
                    "semantic_hint": "temporal",
                    "parsed_ratio": float(
                        self._coerce_sample_to_datetime(sample).notna().mean()
                    )
                })
            else:
                # String / categorical / id-like
                sample_str = sample.astype(str)
                lengths = sample_str.str.len()

                profile.update({
                    "semantic_hint": "textual",
                    "avg_length": float(lengths.mean()),
                    "matches_email": any(self.EMAIL_RE.match(v) for v in sample_str),
                    "matches_uuid": any(self.UUID_RE.match(v) for v in sample_str)
                })

            profiles[col] = profile

        return profiles
