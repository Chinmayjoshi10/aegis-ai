from typing import Dict, List, Any

from aegis_ai.company_brain.models import (
    CompanyInsight,
    Impact,
    Evidence,
    generate_insight_id,
    now_ts,
)


PATTERN_CONFIDENCE_THRESHOLD = 0.70
DRIFT_CONFIDENCE_THRESHOLD = 0.80


def synthesize_single_metric_insights(
    *,
    reality_snapshot: Dict[str, Any],
    pattern_signals: List[Dict[str, Any]],
    drift_report: Dict[str, Any],
    quality_report: Dict[str, Any],
) -> List[CompanyInsight]:
    """
    Phase 2A.1 — Single-Metric Insight Generation

    Produces exactly one insight per affected metric.
    Silence is valid and expected for stable systems.
    """

    # -------------------------
    # Guardrail: data integrity
    # -------------------------
    if quality_report.get("blocking_issues"):
        return []

    insights: Dict[str, CompanyInsight] = {}

    # -------------------------
    # Pattern-based insights (highest priority)
    # -------------------------
    for signal in pattern_signals:
        metric = signal.get("metric")
        confidence = signal.get("confidence", 0.0)

        if not metric or confidence < PATTERN_CONFIDENCE_THRESHOLD:
            continue

        # Enforce one insight per metric
        if metric in insights:
            continue

        severity = "high" if confidence >= 0.85 else "medium"

        insights[metric] = CompanyInsight(
            id=generate_insight_id("anomaly"),
            type="anomaly",
            summary=f"Unusual behavior detected in '{metric}'",
            severity=severity,
            confidence=confidence,
            impact=Impact(
                metrics=[metric],
                direction="unknown",
                magnitude="moderate",
            ),
            evidence=Evidence(
                reality_metrics=reality_snapshot.get(metric, {}),
                pattern_signals=[signal],
                drift=drift_report.get(metric),
            ),
            recommended_attention=True,
            created_at=now_ts(),
        )

    # -------------------------
    # Drift-only insights (only if no anomaly)
    # -------------------------
    for metric, drift in drift_report.items():
        if metric in insights:
            continue

        drift_score = drift.get("drift_score", 0.0)

        if drift_score < DRIFT_CONFIDENCE_THRESHOLD:
            continue

        insights[metric] = CompanyInsight(
            id=generate_insight_id("drift"),
            type="drift",
            summary=f"'{metric}' is drifting from its historical baseline",
            severity="medium",
            confidence=drift_score,
            impact=Impact(
                metrics=[metric],
                direction="unknown",
                magnitude="small",
            ),
            evidence=Evidence(
                reality_metrics=reality_snapshot.get(metric, {}),
                pattern_signals=[],
                drift=drift,
            ),
            recommended_attention=True,
            created_at=now_ts(),
        )

    return list(insights.values())
