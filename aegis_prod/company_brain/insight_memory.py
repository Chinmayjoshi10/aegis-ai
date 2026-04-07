import time
import hashlib
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from aegis_ai.db.models.insight_ledger import InsightLedger
from aegis_ai.company_brain.trajectory import TrajectoryEngine


def _hash_evidence(evidence: Dict[str, Any]) -> str:
    """
    Create a stable hash so identical insights don't spam the ledger.
    """
    raw = repr(sorted(evidence.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_insight_history(
    *,
    db: Session,
    primitive: str,
    metric: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Load recent historical insights for lineage comparison.

    FAIL-OPEN:
    - Any failure returns empty history
    - No DB schema assumptions beyond existing fields
    """

    try:
        rows = (
            db.query(InsightLedger)
            .filter(InsightLedger.primitive == primitive)
            .filter(InsightLedger.metric == metric)
            .order_by(InsightLedger.observed_at.desc())
            .limit(limit)
            .all()
        )

        history = []
        for r in rows:
            history.append({
                "primitive": r.primitive,
                "metric": r.metric,
                "confidence": r.confidence,
                "signal_score": None,  # may be missing in DB, allowed
                "observed_at": r.observed_at,
                # lineage_key will be recomputed
            })

        return history

    except Exception:
        return []


def record_insight(
    *,
    db: Session,
    insight: Dict[str, Any],
) -> None:
    """
    Persist a high-confidence insight to the ledger.

    SAFE EXTENSION:
    - Trajectory Phase A annotation (lineage, persistence, velocity)
    - Fail-open: trajectory failure NEVER blocks persistence
    """

    try:
        # -------------------------------------------------
        # TRAJECTORY PHASE A (SAFE, ADDITIVE)
        # -------------------------------------------------
        try:
            trajectory_engine = TrajectoryEngine()

            history = _load_insight_history(
                db=db,
                primitive=insight.get("primitive"),
                metric=insight.get("metric"),
            )

            annotated = trajectory_engine.annotate(
                insights=[insight],
                insight_history=history,
            )

            if annotated:
                insight = annotated[0]

        except Exception:
            # Trajectory must NEVER block persistence
            pass

        # -------------------------------------------------
        # LEDGER WRITE (UNCHANGED)
        # -------------------------------------------------
        ledger_row = InsightLedger(
            primitive=insight["primitive"],
            metric=insight["metric"],
            subtype=insight.get("subtype"),
            confidence=float(insight["confidence"]),
            scope="GLOBAL",
            evidence_hash=_hash_evidence(insight.get("evidence", {})),
            observed_at=int(time.time()),
        )

        db.add(ledger_row)
        db.commit()

    except Exception:
        # ABSOLUTELY NO EXCEPTIONS ESCAPE
        db.rollback()
