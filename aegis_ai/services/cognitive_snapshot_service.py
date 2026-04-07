import uuid
from datetime import datetime
from sqlalchemy.orm import Session

from aegis_ai.db.models.cognitive_snapshots import CognitiveSnapshot


class CognitiveSnapshotService:

    @staticmethod
    def compute_health_score(system_state: str, insight_count: int) -> float:
        if system_state == "INSIGHTFUL":
            return min(0.6 + 0.1 * insight_count, 1.0)
        if system_state == "SILENT":
            return 0.75
        return 0.5

    @staticmethod
    def persist(
        *,
        db: Session,
        tenant: str,
        brain_name: str,
        model_version: str,
        system_state: str,
        insights: list,
        snapshot_blob: dict,
    ):

        health_score = CognitiveSnapshotService.compute_health_score(
            system_state,
            len(insights),
        )

        snapshot = CognitiveSnapshot(
            tenant=tenant,
            snapshot_id=str(uuid.uuid4()),
            brain_name=brain_name,
            model_version=model_version,
            health_score=health_score,
            snapshot_blob=snapshot_blob,
            created_at=datetime.utcnow(),
        )

        db.add(snapshot)
        db.commit()