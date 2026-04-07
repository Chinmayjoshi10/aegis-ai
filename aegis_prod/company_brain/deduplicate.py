from typing import List, Dict, Tuple
from collections import defaultdict

from aegis_ai.company_brain.models import CompanyInsight, Impact, Evidence


MERGE_PRIORITY = {
    "risk": 3,
    "anomaly": 2,
    "drift": 1,
    "stability": 0,
}


def _merge_types(a: str, b: str) -> str:
    return a if MERGE_PRIORITY[a] >= MERGE_PRIORITY[b] else b


def _merge_severity(a: str, b: str) -> str:
    order = {"low": 1, "medium": 2, "high": 3}
    return a if order[a] >= order[b] else b


def _merge_confidence(a: float, b: float) -> float:
    # conservative: never inflate beyond strongest signal
    return max(a, b)


def _merge_evidence(e1: Evidence, e2: Evidence) -> Evidence:
    return Evidence(
        reality_metrics={**e1.reality_metrics, **e2.reality_metrics},
        pattern_signals=e1.pattern_signals + e2.pattern_signals,
        drift=e1.drift or e2.drift,
    )


def deduplicate_and_merge_insights(
    insights: List[CompanyInsight],
) -> List[CompanyInsight]:
    """
    Phase 2A.3 — Deduplicate and merge overlapping insights.

    Returns a reduced list of canonical insights.
    """

    buckets: Dict[Tuple[str, Tuple[str, ...]], List[CompanyInsight]] = defaultdict(list)

    # Bucket by (primary_metric, sorted_metrics)
    for insight in insights:
        metrics = tuple(sorted(insight.impact.metrics))
        primary = metrics[0] if metrics else "global"
        buckets[(primary, metrics)].append(insight)

    merged: List[CompanyInsight] = []

    for _, group in buckets.items():
        if len(group) == 1:
            merged.append(group[0])
            continue

        base = group[0]

        for other in group[1:]:
            base = CompanyInsight(
                id=base.id,  # keep original canonical ID
                type=_merge_types(base.type, other.type),
                summary=base.summary,
                severity=_merge_severity(base.severity, other.severity),
                confidence=_merge_confidence(
                    base.confidence, other.confidence
                ),
                impact=Impact(
                    metrics=base.impact.metrics,
                    direction=base.impact.direction,
                    magnitude=base.impact.magnitude,
                ),
                evidence=_merge_evidence(base.evidence, other.evidence),
                recommended_attention=(
                    base.recommended_attention
                    or other.recommended_attention
                ),
                created_at=base.created_at,
            )

        merged.append(base)

    return merged
