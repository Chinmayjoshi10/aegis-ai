# aegis_ai/persistence/cognitive_snapshot_repository.py

from sqlalchemy.orm import Session
from aegis_ai.db.models.cognitive_snapshots import CognitiveSnapshot


class CognitiveSnapshotRepository:

    @staticmethod
    def save(db: Session, snapshot_data: dict) -> None:
        """
        Persists cognitive snapshot to database.
        """

        snapshot = CognitiveSnapshot(**snapshot_data)

        db.add(snapshot)
        db.commit()