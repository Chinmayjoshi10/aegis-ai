"""
AEGIS Column Intelligence Filter
==================================
Determines which columns are genuine business metrics
vs technical encodings, IDs, or cyclic columns.

Universal — works across all domains and datasets.
Deterministic — same input always produces same decision.
Fail-open — when uncertain, include the column.
"""

import re
from typing import Optional
import pandas as pd


# ─────────────────────────────────────────────────────
# HARD-EXCLUDE NAME PATTERNS
# Columns whose names indicate they are never business metrics
# ─────────────────────────────────────────────────────

_EXCLUDE_EXACT = {
    # Cyclic temporal encodings
    "nsm", "seconds_since_midnight", "time_of_day_seconds",
    "day_of_year", "week_of_year", "month_of_year",
    "hour_of_day", "minute_of_hour", "second_of_minute",
    # Row identifiers
    "id", "idx", "index", "row_id", "row_number",
    "seq", "sequence", "sequence_id",
    # Raw timestamps
    "unix_timestamp", "epoch", "timestamp_ms", "timestamp_s",
    # Geographic coordinates (not business metrics)
    "latitude", "longitude", "lat", "lng", "lon",
    "country", "order_country", "customer_country",
    "order_state", "customer_state", "order_region",
    # Postal/zip codes (geographic, not metrics)
    "zipcode", "zip_code", "zip", "postal_code", "postcode", "pincode",
    # PII fields (never business metrics)
    "email", "password", "phone", "mobile", "ssn", "pan",
    "credit_card", "card_number", "cvv",
    # Text/description fields
    "description", "notes", "comments", "remarks", "address",
    "street", "city", "country", "state", "name",
}

_EXCLUDE_CONTAINS_WORDS = {
    "zipcode", "zip_code", "postal",
    "password", "email", "latitude", "longitude",
    "description", "address", "street", "city",
    "fname", "lname", "country",
    "firstname", "lastname", "fullname",
}

_EXCLUDE_STARTSWITH = (
    "unnamed",
    "unnamed:",
)

_EXCLUDE_CONTAINS = (
    "_id",       # customer_id, order_id, product_id etc
    "_key",      # surrogate keys
    "_pk",       # primary keys
    "_fk",       # foreign keys
)

# Column names that are ALWAYS valid metrics regardless of other signals
_FORCE_INCLUDE = {
    "revenue", "sales", "cost", "profit", "margin", "quantity",
    "price", "amount", "units", "volume", "rate", "score",
    "headcount", "total", "sum", "avg", "average", "ratio",
}


# ─────────────────────────────────────────────────────
# NAME-BASED FILTER (no data needed)
# ─────────────────────────────────────────────────────

def is_valid_column_name(col: str) -> bool:
    """
    Returns False if the column name indicates it is
    a technical encoding, ID, or cyclic field.
    Returns True if it should be analyzed as a metric.
    """
    c = col.strip().lower()
    normalized = re.sub(r"[_\-\.\s]+", "_", c).strip("_")

    # Force include known business metric names
    if any(fm in normalized for fm in _FORCE_INCLUDE):
        return True

    # Hard exclude by exact match
    if normalized in _EXCLUDE_EXACT or c in _EXCLUDE_EXACT:
        return False

    # Hard exclude by prefix
    if c.startswith(_EXCLUDE_STARTSWITH):
        return False

    # Hard exclude by suffix/contains patterns
    if any(pattern in normalized for pattern in _EXCLUDE_CONTAINS):
        return False

    # Hard exclude by word-level match (e.g. "customer_zipcode" contains "zipcode")
    for word in _EXCLUDE_CONTAINS_WORDS:
        if word in normalized:
            return False

    return True


# ─────────────────────────────────────────────────────
# DATA-BASED FILTER (uses column values)
# Applied in RealityReader after name filter passes
# ─────────────────────────────────────────────────────

def is_metric_column(
    col: str,
    series: pd.Series,
    *,
    min_unique_ratio: float = 0.0005,
    max_cyclic_unique: int = 200,
    cyclic_range_max: float = 90000,
) -> tuple[bool, Optional[str]]:
    """
    Returns (is_metric, reason_if_excluded).

    Detects columns that are numeric but are actually:
    - Cyclic time encodings (NSM, hour, day-of-year)
    - Degenerate columns with almost no variation
    - Pure row counters

    Fail-open: returns (True, None) when uncertain.
    """

    # Name filter first
    if not is_valid_column_name(col):
        return False, "excluded_by_name"

    s = series.dropna()
    if len(s) == 0:
        return False, "empty_column"

    n_unique = s.nunique()
    n_rows = len(s)
    unique_ratio = n_unique / max(n_rows, 1)

    # Degenerate — single value (constant column like Product Status = all 0s)
    if n_unique <= 1:
        return False, "constant_column"

    # All zeros — no information content
    if (s == 0).all():
        return False, "all_zeros"

    # Check for redacted/masked PII (e.g. all values = "XXXXXXXXX")
    # By the time we get here it's numeric — but string columns get caught by name filter

    # Check for sequential row ID pattern
    # e.g. Order Item Id: values 1 to 180519 perfectly sequential
    try:
        if n_unique == n_rows:
            sorted_vals = sorted(s.values)
            is_sequential = (
                sorted_vals[-1] - sorted_vals[0] == n_rows - 1
                and sorted_vals[0] >= 0
            )
            if is_sequential:
                return False, "sequential_id"
    except Exception:
        pass

    # Check for cyclic integer encoding pattern
    # e.g. NSM: integer values, low unique count, bounded range
    try:
        is_integer_like = (s == s.round(0)).all() and s.dtype in (
            "int32", "int64", "float32", "float64"
        )
        val_range = float(s.max() - s.min())

        if (
            is_integer_like
            and n_unique <= max_cyclic_unique
            and unique_ratio < 0.005
            and 0 <= float(s.min())
            and val_range <= cyclic_range_max
        ):
            return False, "likely_cyclic_encoding"

    except Exception:
        pass  # fail-open

    return True, None 