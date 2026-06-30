# aegis_ai/company_brain/orchestrator_v2.py

import time
import logging
from typing import Dict, Any, List, Optional

import pandas as pd

# ──────────────────────────────────────────────────────
# SAFE IMPORT (NO HARD FAILURE)
# ──────────────────────────────────────────────────────
try:
    from .metric_roles import resolve_metric_roles
except ImportError:
    def resolve_metric_roles(*args, **kwargs):
        return {}

from .dominance_detector import DominanceDetector
from .bias_detector import BiasDetector
from .tradeoff_detector import TradeoffDetector
from .confidence_engine import compute_confidence
from .system_state import (
    resolve_system_state,
    SystemState,
)

log = logging.getLogger("aegis_ai.company_brain.v2")


# ──────────────────────────────────────────────────────
# COMPANY BRAIN V2 — PRODUCTION SAFE
# ──────────────────────────────────────────────────────
def run_company_brain_v2(
    *,
    df: pd.DataFrame,
    historical_row_count: int,
    baseline_numeric_stats: Dict[str, Dict[str, float]],
    bias_baseline_stats: Dict[str, Dict[str, float]] | None = None,
    domain: str = "data",
) -> Dict[str, Any]:

    start_ts = time.time()
    final_insights: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []

    # ── 0. Metric Role Resolution ──────────────────────
    try:
        metric_roles = resolve_metric_roles(
            df=df,
            baseline_stats=baseline_numeric_stats,
        )
    except Exception as e:
        log.warning(f"metric_roles failed: {e}")
        metric_roles = {}

    # ── 1. Behavioral Primitive Detection ─────────────
    try:
        result = DominanceDetector().detect(df=df)
        if isinstance(result, list):
            candidates.extend(result)
    except Exception as e:
        log.error(f"DominanceDetector failed: {e}", exc_info=True)

    try:
        # Use previous baseline if available; otherwise fall back to
        # current-upload stats for intra-dataset drift detection.
        # CUSUM still detects within-dataset trends (early vs late rows)
        # even when baseline == current stats.
        _bias_stats = bias_baseline_stats or baseline_numeric_stats
        if _bias_stats:
            result = BiasDetector().detect(
                df=df,
                baseline_stats=_bias_stats,
            )
        else:
            result = []  # No stats at all → no bias detection
        if isinstance(result, list):
            candidates.extend(result)
    except Exception as e:
        log.error(f"BiasDetector failed: {e}", exc_info=True)

    try:
        result = TradeoffDetector().detect(
            df=df,
            metric_stats=baseline_numeric_stats,
        )
        if isinstance(result, list):
            candidates.extend(result)
    except Exception as e:
        log.error(f"TradeoffDetector failed: {e}", exc_info=True)

    # ── 2. Confidence Gating ───────────────────────────
    for candidate in candidates:
        try:
            # F-03: Default persistence/consistency to 0.7 (neutral-positive).
            # 1.0 = "confirmed across 12 months / all segments" — not earned.
            # 0.7 = "no counter-evidence" — honest default that doesn't
            #        penalise first-upload signals for missing temporal data.
            # 0.5 was too conservative: it created a confidence ceiling of
            #        ~0.725, making INSIGHTFUL state nearly unreachable.
            confidence = compute_confidence(
                row_count=historical_row_count,
                signal_score=candidate.get("signal_score", 0.0),
                temporal_persistence_score=0.7,
                consistency_score=0.7,
                penalty_score=0.0,
            )

            candidate["low_confidence"] = confidence < 0.7

            final_insights.append({
                "primitive": candidate.get("primitive"),
                "subtype": candidate.get("subtype"),
                "metric": candidate.get("metric"),
                "metrics": candidate.get("metrics"),
                "summary": _generate_summary(candidate),
                "confidence": round(confidence, 3),
                "evidence": candidate.get("evidence", {}),
                "direction": candidate.get("direction"),
                "signal_score": candidate.get("signal_score"),
            })

        except Exception as e:
            log.warning(f"candidate processing failed: {e}")
            continue
            

    # ── 3. Resolve System State ────────────────────────
    try:
        system_state = resolve_system_state(
            row_count=historical_row_count,
            insights=final_insights,
        )
    except Exception as e:
        log.error(f"system_state resolution failed: {e}", exc_info=True)
        system_state = SystemState.OBSERVATION

    # ── 4. Narrative Layer ────────────────────────────
    try:
        narrative = generate_narrative(
            system_state=system_state,
            insights=final_insights,
            domain=domain,
            row_count=historical_row_count,
        )
    except Exception as e:
        log.warning(f"narrative generation failed: {e}")
        narrative = ""

    # ── Final Output ───────────────────────────────────
    return {
        "system_state": system_state.value,
        "narrative": narrative,
        "insights": final_insights,
        "metric_roles": metric_roles,  # F-04: pass through for event_engine
        "metadata": {
            "candidate_count": len(candidates),
            "final_insight_count": len(final_insights),
            "row_count": historical_row_count,
            "domain": domain,
            "processing_time_sec": round(time.time() - start_ts, 4),
        },
    }


# ──────────────────────────────────────────────────────
# NARRATIVE GENERATOR
# Converts AEGIS output into plain English
# A CFO with zero data background should understand this
# ──────────────────────────────────────────────────────
def generate_narrative(
    system_state: SystemState,
    insights: List[Dict[str, Any]],
    domain: str,
    row_count: int,
) -> str:

    if system_state == SystemState.OBSERVATION:
        return (
            f"AEGIS is still building its baseline for your {domain} data. "
            f"Only {row_count:,} rows were provided — more data is needed "
            "to activate full intelligence. "
            "Upload more data to begin detecting structural patterns."
        )

    if system_state == SystemState.SILENT:
        return (
            f"AEGIS has analyzed your {domain} data and found no structural "
            "patterns that meet the confidence threshold. "
            "Your system appears to be operating within expected parameters. "
            "Silence is intentional — AEGIS only speaks when it is certain."
        )

    # INSIGHTFUL — build sentences from confirmed insights
    sentences = []

    bias_insights = [i for i in insights if i.get("primitive") == "BIAS"]
    dominance_insights = [i for i in insights if i.get("primitive") == "DOMINANCE"]
    tradeoff_insights = [i for i in insights if i.get("primitive") == "TRADEOFF"]

    total = len(insights)
    sentences.append(
        f"AEGIS has detected {total} structural pattern{'s' if total != 1 else ''} "
        f"in your {domain} data with sufficient confidence to report."
    )

    top_signal = max(insights, key=lambda x: (x.get("confidence", 0), x.get("signal_score", 0))) if insights else None
    if top_signal:
        ts_type = top_signal.get("primitive", "Signal")
        ts_metric = top_signal.get("metric", "A key metric")
        ts_score = int(top_signal.get("signal_score", 0) * 100)
        sentences.append(f"The most dominant structural pattern is a {ts_score}% confidence {ts_type} involving {ts_metric}.")

    for b in bias_insights[:2]:
        direction = b.get("subtype", "").lower()
        metric = b.get("metric", "A metric")
        conf = int(b.get("confidence", 0) * 100)
        sentences.append(
            f"{metric} has been drifting persistently {direction} "
            f"from its historical baseline ({conf}% confidence)."
        )

    for d in dominance_insights[:2]:
        metric = d.get("metric", "A metric")
        subtype = d.get("subtype", "")
        conf = int(d.get("confidence", 0) * 100)

        if subtype == "CATEGORICAL":
            sentences.append(
                f"{metric} is dominated by a single category "
                f"({conf}% confidence) — this represents a structural "
                "concentration risk."
            )
        elif subtype == "POINT":
            sentences.append(
                f"{metric} is dominated by a single repeated value "
                f"({conf}% confidence) — this may indicate automation, "
                "fixed pricing, or a data entry pattern."
            )
        elif subtype in ("RANGE_STD", "RANGE_QUANTILE"):
            sentences.append(
                f"{metric} is operating in an unusually tight range "
                f"({conf}% confidence) — this may indicate a system "
                "cap, throttle, or operational constraint."
            )

    for t in tradeoff_insights[:1]:
        metrics = t.get("metrics") or ["Metric A", "Metric B"]
        conf = int(t.get("confidence", 0) * 100)
        pair_class = t.get("evidence", {}).get("pair_classification", "UNKNOWN")
        if len(metrics) >= 2:
            # F-02: Use pair classification for economically correct language
            if pair_class == "CONFLICT":
                sentences.append(
                    f"A conflict exists between {metrics[0]} and {metrics[1]}: "
                    f"these metrics are moving in opposite directions when they "
                    f"should move together ({conf}% confidence)."
                )
            else:
                sentences.append(
                    f"A structural tradeoff exists between {metrics[0]} and "
                    f"{metrics[1]}: improving one is associated with deterioration "
                    f"in the other ({conf}% confidence)."
                )

    return " ".join(sentences)


# ──────────────────────────────────────────────────────
# SUMMARY GENERATOR — per-insight one-liner
# ──────────────────────────────────────────────────────
def _generate_summary(candidate: Dict[str, Any]) -> str:
    primitive = candidate.get("primitive")
    subtype = candidate.get("subtype")
    # `direction` is set by the correctness layer once actual change is known.
    # If it disagrees with the detector's subtype (e.g. BIAS detector fired
    # but actual change was within the FLAT band), direction is authoritative.
    direction_field = (candidate.get("direction") or "").upper()
    metric_name = candidate.get("metric") or "This metric"

    if primitive == "DOMINANCE":
        if subtype in ("RANGE_STD", "RANGE_QUANTILE"):
            return "This metric operates within a tightly constrained range."
        if subtype == "POINT":
            return "This metric is dominated by a single repeated value."
        if subtype == "CATEGORICAL":
            return "This metric is governed by a single dominant category."

    if primitive == "BIAS":
        # Guard: BIAS + FLAT actual direction is a semantic contradiction.
        # Emit a stability statement instead of a "drifting" one.
        if direction_field in ("FLAT", "STABLE", "NONE"):
            return (
                f"{metric_name} is stable — no significant directional drift "
                f"detected relative to its historical baseline."
            )
        direction = subtype.lower() if subtype else "directionally"
        return (
            f"This metric is persistently drifting "
            f"{direction} from its historical baseline."
        )

    if primitive in ("STABLE", "NONE"):
        return (
            f"{metric_name} is stable — no significant movement detected "
            f"relative to its historical baseline."
        )

    if primitive == "TRADEOFF":
        metrics = candidate.get("metrics") or ("Metric A", "Metric B")
        a = metrics[0] if len(metrics) > 0 else "Metric A"
        b = metrics[1] if len(metrics) > 1 else "Metric B"
        return (
            f"Improvement in {a} is statistically associated with "
            f"increased instability or risk in {b}. "
            f"This indicates a structural tradeoff."
        )

    return "A structural behavioral pattern was detected."
