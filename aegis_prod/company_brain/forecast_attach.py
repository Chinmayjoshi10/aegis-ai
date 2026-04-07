from typing import List, Dict, Any

from aegis_ai.company_brain.models import CompanyInsight
from aegis_ai.company_brain.forecast_models import ForecastRisk


def attach_forecasts_to_insights(
    *,
    insights: List[CompanyInsight],
    forecasts: Dict[str, ForecastRisk],  # keyed by metric
) -> List[CompanyInsight]:
    """
    Attach ForecastRisk to insights when applicable.
    """

    for ins in insights:
        metrics = ins.impact.metrics if ins.impact else []
        for m in metrics:
            fr = forecasts.get(m)
            if fr:
                # attach safely
                setattr(ins, "forecast_risk", fr.to_dict())
    return insights
