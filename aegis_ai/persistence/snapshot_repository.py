# aegis_ai/persistence/snapshot_repository.py

from aegis_ai.db.models.cognitive_snapshots import CognitiveSnapshot
from aegis_ai.db.session import SessionLocal


class SnapshotRepository:

    @staticmethod
    def save(snapshot_data: dict) -> None:
        db = SessionLocal()
        try:
            obj = CognitiveSnapshot(**snapshot_data)
            db.add(obj)
            db.commit()
        finally:
            db.close()