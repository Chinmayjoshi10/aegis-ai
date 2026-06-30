"""
aegis_ai/core/dataset_profiler.py
===================================
Universal Dataset Profiler — runs BEFORE the pipeline on every request.

Responsibilities:
  - Detect time column (ISO string OR composite YEAR/MONTH integers)
  - Classify every column as: metric | dimension | identifier | ignored
  - Compute per-column and dataset-level quality scores
  - Surface what was excluded and why (no silent drops)

Contract:
  - Deterministic: same df → same profile every time
  - Fail-open: one bad column never blocks the rest
  - No hardcoded domain logic — generalises across any schema
  - Never reads data values for column classification (name + dtype only),
    then uses data only to confirm/deny the name-based decision
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION PATTERNS  (name-based, order matters)
# ─────────────────────────────────────────────────────────────────────────────

_ID_NAMES = re.compile(
    r"(?:^|_)(id|code|key|number|no|num|pk|fk|ref|uuid|guid|sku|serial|index|idx|barcode|hash|token|nonce)(?:$|_)"
    r"|(?:No|ID|Id|Code|Key|Num|Ref|Idx)$",
    re.IGNORECASE,
)

_TEMPORAL_EXACT = re.compile(
    r"^(year|yr|fiscal_year|fy|month|mo|mth|quarter|qtr|week|wk|day|date"
    r"|timestamp|datetime|time|created_at|updated_at|order_date|posting_date"
    r"|event_time|recorded_at|logged_at|occurred_at|invoice_date|ship_date"
    r"|delivery_date|transaction_date|purchase_date|sale_date|booking_date)$",
    re.IGNORECASE,
)

_TEMPORAL_CONTAINS = re.compile(
    r"(date|time|timestamp|created|updated|posted|recorded|occurred|dispatched"
    r"|delivered|shipped|invoiced|booked|opened|closed|started|ended|at$|_dt$)",
    re.IGNORECASE,
)

_CATEGORICAL_NAMES = re.compile(
    r"\b(type|category|cat|segment|tier|class|status|flag|label|group|region"
    r"|zone|territory|channel|platform|gender|country|state|city|supplier"
    r"|vendor|brand|department|team|role|level|grade|priority|source|medium"
    r"|campaign|product|item|sku_name|name|description|keyword|tag)\b",
    re.IGNORECASE,
)

_METRIC_FORCE_INCLUDE = re.compile(
    r"\b(revenue|sales|cost|acquisition|profit|margin|quantity|qty|price|amount|units"
    r"|volume|rate|score|headcount|total|sum|avg|average|ratio|spend|budget"
    r"|roi|ctr|cvr|roas|cpc|cpm|impressions|clicks|conversions|sessions"
    r"|bounce|retention|churn|attrition|salary|wage|transfers|transfer"
    r"|defects|downtime|uptime|oee|emissions|energy|power|flow|yield"
    r"|inventory|stock|orders|returns|refunds|complaints|tickets|incidents"
    r"|sentiment|satisfaction|nps|rating|discount|rebate|tax|duty)\b",
    re.IGNORECASE,
)

_PII_NAMES = re.compile(
    r"\b(email|password|phone|mobile|ssn|pan|cvv|card|credit|debit|passport"
    r"|license|address|street|postcode|zipcode|postal|latitude|longitude"
    r"|lat|lng|lon|ip_address|mac_address)\b",
    re.IGNORECASE,
)

# Coefficient of variation above which a numeric column is likely an identifier
_CV_ID_THRESHOLD = 3.0

# Max cardinality ratio for a column to be treated as categorical (not free text)
_MAX_CATEGORICAL_UNIQUE_RATIO = 0.05

# Min rows a column must have non-null for us to profile it
_MIN_VALID_ROWS = 10


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ColumnProfile:
    name: str
    dtype: str
    role: str                      # metric | dimension | temporal | identifier | ignored
    reason: str                    # why this role was assigned
    null_ratio: float = 0.0
    zero_ratio: float = 0.0
    unique_ratio: float = 0.0
    cv: float = 0.0                # coefficient of variation (numeric only)
    n_unique: int = 0
    n_rows: int = 0


@dataclass
class DatasetProfile:
    time_column: Optional[str]                   # best ISO date column (or None)
    year_column: Optional[str]                   # YEAR integer column (composite path)
    month_column: Optional[str]                  # MONTH integer column (composite path)
    valid_metrics: list[str]                     # columns safe for CUSUM / dominance
    dimensions: list[str]                        # categorical columns for segmentation
    ignored_columns: list[str]                   # identifiers, PII, free text
    temporal_columns: list[str]                  # all date/time columns found
    column_profiles: list[ColumnProfile]         # per-column detail
    data_quality_score: float                    # 0.0–1.0
    ordered_data: bool                           # True if temporal structure detected
    row_count: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["column_profiles"] = [asdict(cp) for cp in self.column_profiles]
        return d


# ─────────────────────────────────────────────────────────────────────────────
# PROFILER
# ─────────────────────────────────────────────────────────────────────────────

class DatasetProfiler:
    """
    Universal dataset profiler.

    Call: profile = DatasetProfiler().profile(df)
    """

    def profile(self, df: pd.DataFrame) -> DatasetProfile:
        col_profiles: list[ColumnProfile] = []
        warnings: list[str] = []

        for col in df.columns:
            try:
                cp = self._profile_column(col, df[col], len(df))
                col_profiles.append(cp)
            except Exception as e:
                col_profiles.append(ColumnProfile(
                    name=col, dtype=str(df[col].dtype),
                    role="ignored", reason=f"profiling_error: {e}",
                ))

        # ── Classify outputs ───────────────────────────────────────────────
        valid_metrics = sorted([cp.name for cp in col_profiles if cp.role == "metric"])
        dimensions    = sorted([cp.name for cp in col_profiles if cp.role == "dimension"])
        ignored       = sorted([cp.name for cp in col_profiles if cp.role == "ignored"])
        temporals     = sorted([cp.name for cp in col_profiles if cp.role == "temporal"])

        # ── Temporal detection ─────────────────────────────────────────────
        time_col   = self._pick_iso_time_column(df, temporals)
        year_col   = self._pick_year_column(df, col_profiles)
        month_col  = self._pick_month_column(df, col_profiles)
        ordered    = bool(time_col or year_col)

        # ── Quality score ──────────────────────────────────────────────────
        quality = self._compute_quality_score(col_profiles, df)

        # ── Warnings ──────────────────────────────────────────────────────
        for cp in col_profiles:
            if cp.role == "ignored" and "identifier" in cp.reason:
                warnings.append(
                    f"'{cp.name}' excluded — looks like an identifier "
                    f"(reason: {cp.reason})"
                )
            if cp.role == "metric" and cp.zero_ratio > 0.5:
                warnings.append(
                    f"'{cp.name}' is a metric but {cp.zero_ratio*100:.0f}% zeros — "
                    "CUSUM results may be unreliable."
                )

        if not valid_metrics:
            warnings.append(
                "No valid metric columns found. "
                "Check column names or upload a dataset with numeric business metrics."
            )

        if not ordered:
            warnings.append(
                "No temporal column detected. Running in snapshot mode — "
                "CUSUM signals reflect row order, not time order."
            )

        # ── Future timestamp check ─────────────────────────────────────────
        from datetime import datetime
        if time_col and time_col in df.columns:
            try:
                # convert to datetime safely
                temp_time = pd.to_datetime(df[time_col], errors='coerce')
                if not temp_time.empty and temp_time.max() > datetime.utcnow():
                    quality *= 0.1
                    warnings.append(f"Future timestamps detected in {time_col}")
            except Exception:
                pass

        return DatasetProfile(
            time_column=time_col,
            year_column=year_col,
            month_column=month_col,
            valid_metrics=valid_metrics,
            dimensions=dimensions,
            ignored_columns=ignored,
            temporal_columns=temporals,
            column_profiles=col_profiles,
            data_quality_score=quality,
            ordered_data=ordered,
            row_count=len(df),
            warnings=warnings,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # COLUMN CLASSIFIER
    # ─────────────────────────────────────────────────────────────────────────

    def _profile_column(
        self, col: str, series: pd.Series, total_rows: int
    ) -> ColumnProfile:
        c_norm = col.strip().lower()
        c_norm = re.sub(r"[\s\-\.]+", "_", c_norm).strip("_")
        dtype_str = str(series.dtype)

        s = series.dropna()
        n_rows    = len(s)
        n_unique  = s.nunique() if n_rows > 0 else 0
        null_ratio = round(series.isna().mean(), 4)
        unique_ratio = round(n_unique / max(n_rows, 1), 4)

        # ── PII — hard exclude first ──────────────────────────────────────
        if _PII_NAMES.search(c_norm):
            return ColumnProfile(
                name=col, dtype=dtype_str, role="ignored",
                reason="pii_field", null_ratio=null_ratio,
                n_unique=n_unique, n_rows=n_rows, unique_ratio=unique_ratio,
            )

        # ── Temporal — check before ID so "order_date" isn't caught by ID ─
        if _TEMPORAL_EXACT.match(c_norm) or _TEMPORAL_CONTAINS.search(c_norm):
            # Verify it's actually date-parseable or an integer year
            if self._is_parseable_date(series) or self._is_year_column(series, c_norm):
                return ColumnProfile(
                    name=col, dtype=dtype_str, role="temporal",
                    reason="temporal_name_match", null_ratio=null_ratio,
                    n_unique=n_unique, n_rows=n_rows, unique_ratio=unique_ratio,
                )

        # ── Force-include known business metric names ─────────────────────
        if _METRIC_FORCE_INCLUDE.search(c_norm):
            zero_ratio, cv = self._numeric_stats(series)
            return ColumnProfile(
                name=col, dtype=dtype_str, role="metric",
                reason="force_include_metric_name",
                null_ratio=null_ratio, zero_ratio=zero_ratio,
                n_unique=n_unique, n_rows=n_rows, unique_ratio=unique_ratio, cv=cv,
            )

        # ── Identifier by name ────────────────────────────────────────────
        if _ID_NAMES.search(c_norm):
            return ColumnProfile(
                name=col, dtype=dtype_str, role="ignored",
                reason="identifier_name_pattern",
                null_ratio=null_ratio, n_unique=n_unique,
                n_rows=n_rows, unique_ratio=unique_ratio,
            )

        # ── Now use dtype + data ──────────────────────────────────────────
        is_numeric = pd.api.types.is_numeric_dtype(series)

        if is_numeric and n_rows >= _MIN_VALID_ROWS:
            zero_ratio, cv = self._numeric_stats(series)

            # High CV + near-unique values = numeric identifier (ITEM CODE pattern)
            if cv > _CV_ID_THRESHOLD and unique_ratio > 0.5:
                return ColumnProfile(
                    name=col, dtype=dtype_str, role="ignored",
                    reason=f"numeric_identifier_cv_{cv:.1f}x",
                    null_ratio=null_ratio, zero_ratio=zero_ratio,
                    n_unique=n_unique, n_rows=n_rows, unique_ratio=unique_ratio, cv=cv,
                )

            # Constant or all-zero — no business value
            if n_unique <= 1:
                return ColumnProfile(
                    name=col, dtype=dtype_str, role="ignored",
                    reason="constant_column", null_ratio=null_ratio,
                    n_unique=n_unique, n_rows=n_rows,
                )

            # Low-cardinality integer → ONLY dimension if integer AND truly categorical
            if (
                pd.api.types.is_integer_dtype(series)
                and n_unique <= 20
                and unique_ratio < 0.001
            ):
                return ColumnProfile(
                    name=col, dtype=dtype_str, role="dimension",
                    reason="low_cardinality_integer",
                    null_ratio=null_ratio, zero_ratio=zero_ratio,
                    n_unique=n_unique, n_rows=n_rows, unique_ratio=unique_ratio,
                )

            # Default numeric → metric
            return ColumnProfile(
                name=col, dtype=dtype_str, role="metric",
                reason="numeric_dtype",
                null_ratio=null_ratio, zero_ratio=zero_ratio,
                n_unique=n_unique, n_rows=n_rows, unique_ratio=unique_ratio, cv=cv,
            )

        # ── String/object columns ─────────────────────────────────────────
        if n_rows > 0:
            # Categorical dimension: named like one OR low enough cardinality
            if _CATEGORICAL_NAMES.search(c_norm) or unique_ratio <= _MAX_CATEGORICAL_UNIQUE_RATIO:
                return ColumnProfile(
                    name=col, dtype=dtype_str, role="dimension",
                    reason="categorical_name_or_low_cardinality",
                    null_ratio=null_ratio, n_unique=n_unique,
                    n_rows=n_rows, unique_ratio=unique_ratio,
                )

            # High-cardinality string — likely free text or identifier
            return ColumnProfile(
                name=col, dtype=dtype_str, role="ignored",
                reason="high_cardinality_string",
                null_ratio=null_ratio, n_unique=n_unique,
                n_rows=n_rows, unique_ratio=unique_ratio,
            )

        return ColumnProfile(
            name=col, dtype=dtype_str, role="ignored",
            reason="empty_column", null_ratio=null_ratio,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TEMPORAL HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _is_parseable_date(self, series: pd.Series) -> bool:
        try:
            sample = series.dropna().head(50)
            parsed = pd.to_datetime(sample, errors="coerce")
            return parsed.notna().mean() >= 0.8
        except Exception:
            return False

    def _is_year_column(self, series: pd.Series, col_norm: str) -> bool:
        """Detects YEAR integer columns (2015–2030 range, integer-like)."""
        try:
            s = series.dropna()
            if not pd.api.types.is_numeric_dtype(series):
                return False
            return bool(
                (s >= 2000).all() and (s <= 2035).all()
                and (s == s.round(0)).all()
                and s.nunique() <= 20
            )
        except Exception:
            return False

    def _pick_iso_time_column(
        self, df: pd.DataFrame, temporal_cols: list[str]
    ) -> Optional[str]:
        """
        From all temporal columns, pick the one most likely to be an ISO date string.
        Prefers columns whose values actually parse as dates.
        Returns None if no ISO date column found.
        """
        for col in temporal_cols:
            s = df[col].dropna()
            if pd.api.types.is_numeric_dtype(df[col]):
                continue  # integer years handled separately
            if self._is_parseable_date(s):
                return col
        return None

    def _pick_year_column(
        self, df: pd.DataFrame, profiles: list[ColumnProfile]
    ) -> Optional[str]:
        for cp in profiles:
            c_norm = re.sub(r"[\s\-\.]+", "_", cp.name.strip().lower()).strip("_")
            if re.fullmatch(r"year|yr|fiscal_year|fy", c_norm):
                if self._is_year_column(df[cp.name], c_norm):
                    return cp.name
        return None

    def _pick_month_column(
        self, df: pd.DataFrame, profiles: list[ColumnProfile]
    ) -> Optional[str]:
        for cp in profiles:
            c_norm = re.sub(r"[\s\-\.]+", "_", cp.name.strip().lower()).strip("_")
            if re.fullmatch(r"month|mo|mth", c_norm):
                try:
                    s = df[cp.name].dropna()
                    if (s >= 1).all() and (s <= 12).all() and s.nunique() <= 12:
                        return cp.name
                except Exception:
                    pass
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # NUMERIC STAT HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _numeric_stats(self, series: pd.Series) -> tuple[float, float]:
        """Returns (zero_ratio, cv). Fail-open → (0.0, 0.0)."""
        try:
            s = pd.to_numeric(series, errors="coerce").dropna()
            zero_ratio = round(float((s == 0).mean()), 4)
            mean = abs(float(s.mean()))
            std  = float(s.std())
            cv   = round(std / mean, 4) if mean > 0 else 0.0
            return zero_ratio, cv
        except Exception:
            return 0.0, 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # QUALITY SCORE
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_quality_score(
        self, profiles: list[ColumnProfile], df: pd.DataFrame
    ) -> float:
        """
        Quality score [0.0–1.0] based on:
          - Missing ratio across all columns
          - Ratio of valid metrics to total columns
          - Presence of temporal structure
          - Absence of high null/zero metrics

        Deterministic. No randomness.
        """
        if not profiles:
            return 0.0

        total = len(profiles)
        metrics = [p for p in profiles if p.role == "metric"]
        has_temporal = any(p.role == "temporal" for p in profiles)

        # Component 1: completeness (1 - mean null ratio across all columns)
        avg_null = sum(p.null_ratio for p in profiles) / total
        completeness = round(1.0 - avg_null, 4)

        # Component 2: metric density (what fraction of columns are usable metrics)
        metric_density = round(len(metrics) / max(total, 1), 4)
        metric_density = min(metric_density * 2.0, 1.0)  # scale: 50% density = 1.0

        # Component 3: temporal bonus
        temporal_bonus = 0.1 if has_temporal else 0.0

        # Component 4: metric health (penalise high zero-ratio metrics)
        if metrics:
            avg_zero = sum(m.zero_ratio for m in metrics) / len(metrics)
            metric_health = round(1.0 - (avg_zero * 0.5), 4)  # 50% zero = 0.75 penalty
        else:
            metric_health = 0.5

        score = (
            0.40 * completeness
            + 0.30 * metric_density
            + 0.20 * metric_health
            + 0.10 * (1.0 if has_temporal else 0.0)
        ) + temporal_bonus

        return round(min(score, 1.0), 4)