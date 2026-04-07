from typing import List
import logging
from sqlalchemy import text
from sqlalchemy.engine import Engine

from aegis_ai.company_brain.models import CompanyInsight

logger = logging.getLogger(__name__)


INSERT_SQL = text("""
INSERT INTO company_insights (
    id,
    tenant_id,
    domain,
    insight_type,
    severity,
    confidence,
    summary,
    impact,
    evidence,
    recommended_attention,
    created_at
)
VALUES (
    :id,
    :tenant_id,
    :domain,
    :insight_type,
    :severity,
    :confidence,
    :summary,
    :impact::jsonb,
    :evidence::jsonb,
    :recommended_attention,
    to_timestamp(:created_at)
)
ON CONFLICT (id) DO NOTHING;
""")


def persist_company_insights(
    *,
    engine: Engine,
    tenant_id: str,
    domain: str,
    insights: List[CompanyInsight],
) -> None:
    """
    Phase 2A.5 — Insight Persistence

    Fail-open, append-only persistence of canonical insights.
    """

    if not insights:
        return

    try:
        with engine.begin() as conn:
            for insight in insights:
                payload = insight.to_dict()

                conn.execute(
                    INSERT_SQL,
                    {
                        "id": payload["id"],
                        "tenant_id": tenant_id,
                        "domain": domain,
                        "insight_type": payload["type"],
                        "severity": payload["severity"],
                        "confidence": payload["confidence"],
                        "summary": payload["summary"],
                        "impact": payload["impact"],
                        "evidence": payload["evidence"],
                        "recommended_attention": payload["recommended_attention"],
                        "created_at": payload["created_at"],
                    },
                )

    except Exception as e:
        # Fail-open by design
        logger.exception(
            "Failed to persist company insights (non-blocking): %s", e
        )
