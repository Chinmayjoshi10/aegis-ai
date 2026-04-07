from datetime import datetime
from sqlalchemy.orm import Session

from aegis_ai.db.baselines.reality_baseline import RealityBaseline
from aegis_ai.db.baselines.drift_history import DriftHistory


def persist_reality_snapshot(
    session: Session,
    tenant: str,
    domain: str,
    reality: dict,
):
    """
    Save every upload as a new baseline (time-series memory).
    """

    for category, cols in reality["stats"].items():
        for column, m in cols.items():

            row = RealityBaseline(
                tenant_id=tenant,
                domain=domain,
                category=category,
                column_name=column,

                mean=m.get("mean"),
                median=m.get("median"),
                std=m.get("std"),
                min=m.get("min"),
                max=m.get("max"),

                null_ratio=m.get("null_ratio"),
                zero_ratio=m.get("zero_ratio"),
                outlier_ratio=m.get("outlier_ratio"),

                upload_date=datetime.utcnow(),
            )

            session.add(row)

    session.commit()


def get_last_baseline(
    session: Session,
    tenant: str,
    domain: str,
    category: str,
    column: str,
):
    return (
        session.query(RealityBaseline)
        .filter_by(
            tenant_id=tenant,
            domain=domain,
            category=category,
            column_name=column,
        )
        .order_by(RealityBaseline.upload_date.desc())
        .first()
    )


def persist_drift_event(
    session: Session,
    tenant: str,
    domain: str,
    category: str,
    column: str,
    baseline_date,
    drift_score: float,
    drift_type: str,
    alert: bool,
):
    event = DriftHistory(
        tenant_id=tenant,
        domain=domain,
        category=category,
        column_name=column,
        baseline_date=baseline_date,
        drift_score=drift_score,
        drift_type=drift_type,
        alert=alert,
    )

    session.add(event)
    session.commit()
