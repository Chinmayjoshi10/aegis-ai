from typing import Dict, List, Any

from aegis_ai.company_brain.models import (
    CompanyInsight,
    Impact,
    Evidence,
    generate_insight_id,
    now_ts,
)


# These are intentionally LOWER than alert thresholds
WATCH_PATTERN_THRESHOLD = 0.50
WATCH_DRIFT_THRESHOLD = 0.60


def synthesize_stability_insight(
    *,
    canonical_insights: List[CompanyInsight],
    pattern_signals: List[Dict[str, Any]],
    drift_report: Dict[str, Any],
    quality_report: Dict[str, Any],
) -> List[CompanyInsight]:
    """
    Phase 2A.4 — Stability Insight

    Emits an explicit 'all clear' insight only when the system
    is confidently stable.
    """

    # If any real insight exists → no stability message
    if canonical_insights:
        return []

    # Data quality must be acceptable
    if quality_report.get("blocking_issues"):
        return []

    # Weak pattern signals suppress stability
    for signal in pattern_signals:
        if signal.get("confidence", 0.0) >= WATCH_PATTERN_THRESHOLD:
            return []

    # Weak drift suppresses stability
    for drift in drift_report.values():
        if drift.get("drift_score", 0.0) >= WATCH_DRIFT_THRESHOLD:
            return []

    # All checks passed → explicit stability insight
    return [
        CompanyInsight(
            id=generate_insight_id("stability"),
            type="stability",
            summary="All monitored metrics are stable and within expected ranges",
            severity="low",
            confidence=1.0,
            impact=Impact(
                metrics=[],
                direction="positive",
                magnitude="small",
            ),
            evidence=Evidence(
                reality_metrics={},
                pattern_signals=[],
               drift=None,
            ),
            recommended_attention=False,
            created_at=now_ts(),
        )
    ]
