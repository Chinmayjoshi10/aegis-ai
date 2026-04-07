# aegis_ai/company_brain/prescriptive_engine.py
#
# Phase 2D — Prescriptive signal generation.
# Self-contained. No import from perscriptive_engine (typo file deleted).

from typing import List, Dict, Any

from .prescriptive_models import PrescriptiveSignal
from .actionability import compute_actionability_likelihood
from .urgency import compute_urgency
from .models import CompanyInsight


def generate_prescriptive_signals(
    *,
    insights: List[CompanyInsight],
    metric_series: Dict[str, List[float]],
) -> List[PrescriptiveSignal]:
    """
    Phase 2D — Generate prescriptive priority signals.

    For each insight with an impact analysis, compute:
    - actionability likelihood (can we act on this metric?)
    - urgency (how time-sensitive is the lag?)
    - priority score (combined signal)

    Returns signals sorted highest priority first.
    """

    signals: List[PrescriptiveSignal] = []

    for insight in insights:
        impact = getattr(insight, "impact_analysis", None)
        if not impact:
            continue

        for contributor in impact.contributors:
            try:
                actionability = compute_actionability_likelihood(
                    contributor.metric,
                    metric_series,
                )

                urgency = compute_urgency(contributor.lag)

                priority = (
                    contributor.strength
                    * impact.global_confidence
                    * urgency
                    * actionability
                )

                signals.append(
                    PrescriptiveSignal(
                        insight_id=insight.id,
                        priority_score=min(priority, 1.0),
                        urgency=urgency,
                        actionability_likelihood=actionability,
                        confidence=impact.global_confidence,
                        rationale={
                            "metric": contributor.metric,
                            "lag": contributor.lag,
                            "direction": contributor.direction,
                            "impact_strength": contributor.strength,
                            "confidence": impact.global_confidence,
                        },
                    )
                )

            except Exception:
                continue

    signals.sort(key=lambda s: s.priority_score, reverse=True)
    return signals