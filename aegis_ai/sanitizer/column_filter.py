"""
AEGIS Column Intelligence Filter — Universal Edition
=====================================================
Replaces: aegis_ai/sanitizer/column_filter.py

CHANGES vs original:
  1. High-cardinality numeric ID detection using coefficient of variation
  2. Explicit ITEM CODE / product code detection (numeric, wide range, ID-suffix)
  3. YEAR and MONTH excluded from metric analysis (they are dimensions, not metrics)
  4. Reason string returned from is_metric_column is now more specific
  5. _FORCE_INCLUDE expanded to prevent false exclusions on legitimate metrics
"""

import re
from typing import Optional
import pandas as pd


# ─────────────────────────────────────────────────────
# HARD-EXCLUDE NAME PATTERNS
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
    # Geographic coordinates
    "latitude", "longitude", "lat", "lng", "lon",
    "country", "order_country", "customer_country",
    "order_state", "customer_state", "order_region",
    # Postal codes
    "zipcode", "zip_code", "zip", "postal_code", "postcode", "pincode",
    # PII fields
    "email", "password", "phone", "mobile", "ssn", "pan",
    "credit_card", "card_number", "cvv",
    # Text/description
    "description", "notes", "comments", "remarks", "address",
    "street", "city", "name",
    # NEW: Temporal dimensions (not metrics)
    "year", "yr", "fiscal_year", "fy",
    "month", "mo", "mth",
    "quarter", "qtr",
    "week", "day",
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
    "_id",
    "_key",
    "_pk",
    "_fk",
    "_code",     # NEW: item_code, product_code, order_code etc
    "_number",   # NEW: order_number, part_number etc
    "_no",       # NEW: invoice_no, part_no etc
)

# Column names that are ALWAYS valid metrics regardless of other signals
_FORCE_INCLUDE = {
    "revenue", "sales", "cost", "profit", "margin", "quantity",
    "price", "amount", "units", "volume", "rate", "score",
    "headcount", "total", "sum", "avg", "average", "ratio",
    "transfers", "transfer",                # inventory/logistics
    "spend", "budget", "roi", "ctr", "cvr", # marketing
    "defects", "downtime", "uptime", "oee",  # operations
    "salary", "wage", "attrition", "churn",  # HR
}

# Coefficient of variation threshold above which a numeric column is
# treated as a likely identifier (numeric ID / product code)
_CV_IDENTIFIER_THRESHOLD = 3.0


# ─────────────────────────────────────────────────────
# NAME-BASED FILTER
# ─────────────────────────────────────────────────────

def is_valid_column_name(col: str) -> bool:
    """
    Returns False if the column name indicates it is a technical encoding,
    ID, or cyclic/dimension field. Returns True if it should be analyzed.
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

    # Hard exclude by word-level match
    for word in _EXCLUDE_CONTAINS_WORDS:
        if word in normalized:
            return False

    return True


# ─────────────────────────────────────────────────────
# DATA-BASED FILTER
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

    Extended to detect:
      - Numeric ID columns (high CV, ID-sounding name)
      - Product/item codes (wide range, low information)
      - Temporal dimensions (YEAR, MONTH etc) — already caught by name filter,
        but enforced here as a second gate
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

    # Degenerate — constant column
    if n_unique <= 1:
        return False, "constant_column"

    # All zeros — no information content
    if (s == 0).all():
        return False, "all_zeros"

    # Sequential row ID pattern
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

    # NEW: High coefficient-of-variation numeric identifier detection
    # ITEM CODE, Product_Code, etc. are numeric but have CV >> 1
    # because they span a wide range (e.g. 2 to 3,480,003) with no
    # business meaning to their magnitude.
    try:
        mean = abs(float(s.mean()))
        std = float(s.std())
        if mean > 0:
            cv = std / mean
            _ID_PATTERN = re.compile(
                r"\b(id|code|key|number|no|num|pk|fk|ref|sku|serial)\b",
                re.IGNORECASE,
            )
            if cv > _CV_IDENTIFIER_THRESHOLD and _ID_PATTERN.search(col):
                return False, f"numeric_identifier_high_cv_{cv:.1f}x"
    except Exception:
        pass  # fail-open

    # Cyclic integer encoding pattern
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
        pass

    return True, None