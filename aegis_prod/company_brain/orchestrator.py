from typing import Dict, Any, List
import logging

from aegis_ai.company_brain.single_metric import synthesize_single_metric_insights
from aegis_ai.company_brain.cross_metric import synthesize_cross_metric_insights
from aegis_ai.company_brain.deduplicate import deduplicate_and_merge_insights
from aegis_ai.company_brain.stability import synthesize_stability_insight

from aegis_ai.company_brain.xgboost_engine import run_xgboost_impact_analysis
from aegis_ai.company_brain.shap_validator import apply_shap_validation

from aegis_ai.company_brain.prophet_engine import run_prophet_risk_forecast
from aegis_ai.company_brain.forecast_attach import attach_forecasts_to_insights

from aegis_ai.company_brain.prescriptive_engine import generate_prescriptive_signals

logger = logging.getLogger(__name__)


def run_company_brain(
    *,
    reality_snapshot: Dict[str, Any],
    pattern_signals: List[Dict[str, Any]],
    drift_report: Dict[str, Any],
    quality_report: Dict[str, Any],
    metric_series: Dict[str, List[float]],
    timestamps: List[Any],
) -> Dict[str, Any]:
    """
    Phase 2 — Company Brain (FULLY INTEGRATED)

    Returns:
      - company_insights
      - prescriptive_signals
    """

    # -------------------------
    # Phase 2A — WHAT
    # -------------------------
    single_metric = synthesize_single_metric_insights(
        reality_snapshot=reality_snapshot,
        pattern_signals=pattern_signals,
        drift_report=drift_report,
        quality_report=quality_report,
    )

    cross_metric = synthesize_cross_metric_insights(
        single_metric_insights=single_metric,
        pattern_signals=pattern_signals,
        drift_report=drift_report,
        reality_snapshot=reality_snapshot,
    )

    canonical = deduplicate_and_merge_insights(single_metric + cross_metric)

    stability = synthesize_stability_insight(
        canonical_insights=canonical,
        pattern_signals=pattern_signals,
        drift_report=drift_report,
        quality_report=quality_report,
    )

    insights = canonical + stability

    # -------------------------
    # Phase 2C — WHY
    # -------------------------
    for insight in insights:
        metrics = insight.impact.metrics if insight.impact else []
        if not metrics:
            continue

        target_metric = metrics[0]
        candidates = [m for m in reality_snapshot.keys() if m != target_metric]

        impact = run_xgboost_impact_analysis(
            target_metric=target_metric,
            candidate_metrics=candidates,
            reality_snapshot=reality_snapshot,
            metric_series=metric_series,
        )

        if impact:
            impact = apply_shap_validation(impact)
            setattr(insight, "impact_analysis", impact.to_dict())

    # -------------------------
    # Phase 2B — WHEN
    # -------------------------
    forecasts = {}

    for metric, series in metric_series.items():
        fr = run_prophet_risk_forecast(
            metric=metric,
            series=series,
            timestamps=timestamps,
        )
        if fr:
            forecasts[metric] = fr

    insights = attach_forecasts_to_insights(
        insights=insights,
        forecasts=forecasts,
    )

    # -------------------------
    # Phase 2D — SO WHAT
    # -------------------------
    prescriptive = generate_prescriptive_signals(
        insights=insights,
        metric_series=metric_series,
    )

    return {
        "company_insights": [i.to_dict() for i in insights],
        "prescriptive_signals": [p.to_dict() for p in prescriptive],
    }
