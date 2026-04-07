from typing import Dict, List, Any
from collections import defaultdict

from aegis_ai.company_brain.models import (
    CompanyInsight,
    Impact,
    Evidence,
    generate_insight_id,
    now_ts,
)


MIN_SHARED_CONFIDENCE = 0.65
MIN_METRICS_FOR_GROUP = 2


def synthesize_cross_metric_insights(
    *,
    single_metric_insights: List[CompanyInsight],
    pattern_signals: List[Dict[str, Any]],
    drift_report: Dict[str, Any],
    reality_snapshot: Dict[str, Any],
) -> List[CompanyInsight]:
    """
    Phase 2A.2 — Cross-Metric Deterministic Reasoning

    Generates higher-order risk insights when multiple metrics
    exhibit coordinated instability.
    """

    if len(single_metric_insights) < MIN_METRICS_FOR_GROUP:
        return []

    # Map metrics that already have insights
    active_metrics = {i.impact.metrics[0]: i for i in single_metric_insights}

    # Group pattern signals by temporal window
    grouped_signals: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for signal in pattern_signals:
        metric = signal.get("metric")
        confidence = signal.get("confidence", 0.0)

        if (
            not metric
            or metric not in active_metrics
            or confidence < MIN_SHARED_CONFIDENCE
        ):
            continue

        window = signal.get("window", "global")
        grouped_signals[window].append(signal)

    insights: List[CompanyInsight] = []

    for window, signals in grouped_signals.items():
        if len(signals) < MIN_METRICS_FOR_GROUP:
            continue

        metrics = sorted({s["metric"] for s in signals})

        confidence = min(s["confidence"] for s in signals)

        insights.append(
            CompanyInsight(
                id=generate_insight_id("cross_metric"),
                type="risk",
                summary=(
                    "Multiple related metrics show coordinated instability "
                    f"({', '.join(metrics)})"
                ),
                severity="high" if len(metrics) >= 3 else "medium",
                confidence=confidence,
                impact=Impact(
                    metrics=metrics,
                    direction="unknown",
                    magnitude="large" if len(metrics) >= 3 else "moderate",
                ),
                evidence=Evidence(
                    reality_metrics={
                        m: reality_snapshot.get(m, {}) for m in metrics
                    },
                    pattern_signals=signals,
                    drift={
                        m: drift_report.get(m)
                        for m in metrics
                        if m in drift_report
                    },
                ),
                recommended_attention=True,
                created_at=now_ts(),
            )
        )

    return insights
