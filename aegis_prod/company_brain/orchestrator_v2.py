import time
from typing import Dict, Any, List

import pandas as pd

from aegis_ai.company_brain.metric_roles import resolve_metric_roles
from aegis_ai.company_brain.dominance_detector import DominanceDetector
from aegis_ai.company_brain.bias_detector import BiasDetector
from aegis_ai.company_brain.tradeoff_detector import TradeoffDetector
from aegis_ai.company_brain.confidence_engine import compute_confidence
from aegis_ai.company_brain.system_state import (
    resolve_system_state,
    SystemState,
)


# ---------------------------------------------------------------------
# COMPANY BRAIN V2 — PURE INTELLIGENCE CORE
# ---------------------------------------------------------------------
def run_company_brain_v2(
    *,
    df: pd.DataFrame,
    historical_row_count: int,
    baseline_numeric_stats: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:

    start_ts = time.time()
    final_insights: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------
    # 0️⃣ Metric Role Resolution
    # ---------------------------------------------------------------
    try:
        metric_roles = resolve_metric_roles(
            df=df,
            baseline_stats=baseline_numeric_stats,
        )
    except Exception:
        metric_roles = {}

    candidates: List[Dict[str, Any]] = []

    # ---------------------------------------------------------------
    # 1️⃣ Behavioral Primitive Detection
    # ---------------------------------------------------------------
    try:
        candidates.extend(
            DominanceDetector().detect(
                df=df,
                metric_roles=metric_roles,
            )
        )
    except Exception:
        pass

    try:
        candidates.extend(
            BiasDetector().detect(
                df=df,
                baseline_stats=baseline_numeric_stats,
                metric_roles=metric_roles,
            )
        )
    except Exception:
        pass

    try:
        candidates.extend(
            TradeoffDetector().detect(
                df=df,
                metric_stats=baseline_numeric_stats,
                metric_roles=metric_roles,
            )
        )
    except Exception:
        pass

    # ---------------------------------------------------------------
    # 2️⃣ Confidence Gating (Silence Enforced)
    # ---------------------------------------------------------------
    for candidate in candidates:
        try:
            confidence = compute_confidence(
                row_count=historical_row_count,
                signal_score=candidate.get("signal_score", 0.0),
                temporal_persistence_score=1.0,
                consistency_score=1.0,
                penalty_score=0.0,
            )

            if confidence < 0.7:
                continue

            final_insights.append({
                "primitive": candidate["primitive"],
                "subtype": candidate.get("subtype"),
                "metric": candidate.get("metric"),
                "metrics": candidate.get("metrics"),
                "summary": _generate_summary(candidate),
                "confidence": round(confidence, 3),
                "evidence": candidate.get("evidence", {}),
            })

        except Exception:
            continue

    # ---------------------------------------------------------------
    # 3️⃣ Resolve System State
    # ---------------------------------------------------------------
    system_state = resolve_system_state(
        row_count=historical_row_count,
        insights=final_insights,
    )

    return {
        "system_state": system_state.value,
        "insights": (
            final_insights
            if system_state == SystemState.INSIGHTFUL
            else []
        ),
        "metadata": {
            "candidate_count": len(candidates),
            "final_insight_count": len(final_insights),
            "row_count": historical_row_count,
            "processing_time_sec": round(time.time() - start_ts, 4),
        },
    }


# ---------------------------------------------------------------------
# Summary Generator (Non-Semantic)
# ---------------------------------------------------------------------
def _generate_summary(candidate: Dict[str, Any]) -> str:
    primitive = candidate.get("primitive")
    subtype = candidate.get("subtype")

    if primitive == "DOMINANCE":
        if subtype in ("RANGE_STD", "RANGE_QUANTILE"):
            return "This metric operates within a tightly constrained range."
        if subtype == "POINT":
            return "This metric is dominated by a single repeated value."
        if subtype == "CATEGORICAL":
            return "This metric is governed by a single dominant category."

    if primitive == "BIAS":
        direction = subtype.lower() if subtype else "directionally"
        return (
            f"This metric is persistently drifting "
            f"{direction} from its historical baseline."
        )

    if primitive == "TRADEOFF":
        a, b = candidate.get("metrics", ("Metric A", "Metric B"))
        return (
            f"Improvement in {a} is statistically associated with "
            f"increased instability or risk in {b}. "
            f"This indicates a structural tradeoff."
        )

    return "A structural behavioral pattern was detected."