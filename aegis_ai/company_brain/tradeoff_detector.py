from typing import Dict, Any, List, Tuple
import re
import numpy as np
import pandas as pd
from scipy.stats import pearsonr


# ─────────────────────────────────────────────────────────────────────────────
# F-02: ECONOMIC POLARITY — determines whether a metric "improving" means
# going UP or going DOWN.  Used to distinguish true tradeoffs from co-movement.
#
#   GOOD_UP:   Revenue, Conversions, Output — improvement = increase
#   GOOD_DOWN: Cost, Defects, Churn        — improvement = decrease
#   NEUTRAL:   Transfer, Inventory          — no inherent direction
# ─────────────────────────────────────────────────────────────────────────────

_POLARITY_KEYWORDS: list[tuple[re.Pattern, str]] = [
    # GOOD_UP — higher is better
    # (?:^|_|\b) matches word boundaries AND underscore-separated compound names
    (re.compile(r"(?:^|_|\b)(revenue|sales|income|turnover|profit|margin|roi|roas|conversion|cvr|ctr|nps|clv|satisfaction|rating|score|efficiency|performance|output|volume|units|quantity|qty|orders|bookings|signups|fill.?rate|oee|on.?time|yield)(?:$|_|\b)", re.I), "GOOD_UP"),
    # GOOD_DOWN — lower is better
    (re.compile(r"(?:^|_|\b)(cost|expense|spend|cogs|opex|capex|overhead|defect|churn|attrition|return|refund|downtime|absence|error|fault|reject|complaint|incident|delay|late|overdue|price|pricing|tariff|fee|discount|cpa|cac|burn)(?:$|_|\b)", re.I), "GOOD_DOWN"),
    # NEUTRAL — no inherent direction
    (re.compile(r"(?:^|_|\b)(transfer|inventory|stock|warehouse|movement|logistics|freight|shipping|headcount|fte|count)(?:$|_|\b)", re.I), "NEUTRAL"),
]


def _infer_polarity(metric_name: str) -> str:
    """Infer economic polarity from metric name. Returns GOOD_UP | GOOD_DOWN | NEUTRAL | UNKNOWN."""
    for pattern, polarity in _POLARITY_KEYWORDS:
        if pattern.search(metric_name):
            return polarity
    return "UNKNOWN"


def _classify_pair_polarity(
    polarity_a: str, polarity_b: str, correlation_sign: float,
) -> str:
    """
    F-02: Classify a metric pair's relationship given their economic polarities
    and observed correlation sign.

    Rules:
      same polarity + positive corr   → CO_MOVEMENT (ignore — expected)
      same polarity + negative corr   → CONFLICT (unexpected — flag)
      opposite polarity + negative corr → EXPECTED (ignore — natural inverse)
      opposite polarity + positive corr → TRUE_TRADEOFF (flag)
      any NEUTRAL or UNKNOWN           → UNKNOWN (pass through for manual review)

    Returns: TRUE_TRADEOFF | CONFLICT | CO_MOVEMENT | EXPECTED | UNKNOWN
    """
    if "UNKNOWN" in (polarity_a, polarity_b) or "NEUTRAL" in (polarity_a, polarity_b):
        return "UNKNOWN"

    same_polarity = (polarity_a == polarity_b)
    positive_corr = (correlation_sign > 0)

    if same_polarity and positive_corr:
        return "CO_MOVEMENT"
    if same_polarity and not positive_corr:
        return "CONFLICT"
    if not same_polarity and not positive_corr:
        return "EXPECTED"
    # opposite polarity + positive correlation
    return "TRUE_TRADEOFF"


class TradeoffDetector:
    """
    Detects structural tradeoffs between stable and risky behaviors.

    Domain-agnostic.
    Behavioral only.

    SAFE EXTENSION:
    - Optionally conditions detection on operating regime
    - Preserves all legacy behavior when regime is absent
    """

    def __init__(
        self,
        *,
        min_points: int = 50,
        corr_threshold: float = 0.3,
        p_value_threshold: float = 0.2,
        max_pairs: int = 20,
    ):
        self.min_points = min_points
        self.corr_threshold = corr_threshold
        self.p_value_threshold = p_value_threshold
        self.max_pairs = max_pairs

    # ---------------------------------------------------------
    # PUBLIC ENTRY
    # ---------------------------------------------------------
    def detect(
        self,
        df: pd.DataFrame,
        metric_stats: Dict[str, Dict[str, float]],
        *,
        regime: Dict[str, str] | None = None,   # ✅ OPTIONAL, NON-BREAKING
    ) -> List[Dict[str, Any]]:

        numeric_cols = [
            c for c in df.columns
            if c in metric_stats and pd.api.types.is_numeric_dtype(df[c])
        ]

        if len(numeric_cols) < 2:
            return []

        tradeoffs: List[Dict[str, Any]] = []

        for i in range(len(numeric_cols)):
            for j in range(i + 1, len(numeric_cols)):
                a = numeric_cols[i]
                b = numeric_cols[j]

                result = self._analyze_pair(df[a], df[b], a, b)
                if result:
                    # -------------------------------
                    # SAFE ADDITIVE METADATA
                    # -------------------------------
                    if regime:
                        result["regime"] = {
                            "load": regime.get("load"),
                            "stress": regime.get("stress"),
                        }

                    tradeoffs.append(result)

        # Sort by signal_score (abs correlation)
        tradeoffs.sort(key=lambda x: x.get("signal_score", 0), reverse=True)
        
        if not tradeoffs:
            return []
            
        # Top 10 tradeoffs only
        tradeoffs = tradeoffs[:10]
        
        # Adaptive thresholding
        if tradeoffs[0].get("signal_score", 0) > 0.4:
            # Strong signals exist, filter out weak noise
            tradeoffs = [t for t in tradeoffs if t.get("signal_score", 0) >= 0.35]

        return tradeoffs

    # ---------------------------------------------------------
    # METRIC CLASSIFICATION (UNCHANGED)
    # ---------------------------------------------------------
    def _classify_metrics(
        self,
        stats: Dict[str, Dict[str, float]],
    ) -> Tuple[List[str], List[str]]:

        stable = []
        risky = []

        for metric, s in stats.items():
            mean = s.get("mean")
            std = s.get("std")
            outliers = s.get("three_sigma_outliers", 0)
            count = s.get("count", 1)

            if not mean or not std or count <= 0:
                continue

            cv = std / abs(mean)

            if cv < 0.15 and outliers / count < 0.01:
                stable.append(metric)

            if outliers / count > 0.02 or cv > 0.35:
                risky.append(metric)

        return stable, risky

    # ---------------------------------------------------------
    # PAIR ANALYSIS — F-02: with economic polarity filter
    # ---------------------------------------------------------
    def _analyze_pair(
        self,
        series_a: pd.Series,
        series_b: pd.Series,
        a: str,
        b: str,
    ) -> Dict[str, Any] | None:

        paired = pd.concat([series_a, series_b], axis=1).dropna()

        if len(paired) < self.min_points:
            return None

        corr, p = pearsonr(paired.iloc[:, 0], paired.iloc[:, 1])

        if abs(corr) < self.corr_threshold or p > self.p_value_threshold:
            return None

        # F-02: Economic polarity filter — classify the pair
        polarity_a = _infer_polarity(a)
        polarity_b = _infer_polarity(b)
        pair_class = _classify_pair_polarity(polarity_a, polarity_b, corr)

        # Filter out co-movements and expected inverse relationships
        if pair_class in ("CO_MOVEMENT", "EXPECTED"):
            return None

        # High-correlation co-movement guard for UNKNOWN polarity pairs.
        # If abs(corr) > 0.70 and both metrics move in the same direction
        # (positive correlation), this is co-movement regardless of whether
        # we can infer polarity. A 0.96 positive correlation between two
        # metrics that both increase is never a tradeoff.
        if pair_class == "UNKNOWN" and corr > 0.70:
            return None

        direction = "POSITIVE" if corr > 0 else "NEGATIVE"
        signal_score = min(abs(corr), 1.0)

        return {
            "primitive": "TRADEOFF",
            "metrics": [a, b],
            "direction": direction,
            "signal_score": signal_score,
            "pair_classification": pair_class,  # TRUE_TRADEOFF | CONFLICT | UNKNOWN
            "polarity": {"a": polarity_a, "b": polarity_b},
            "evidence": {
                "correlation": corr,
                "p_value": p,
                "points": len(paired),
            },
        }
