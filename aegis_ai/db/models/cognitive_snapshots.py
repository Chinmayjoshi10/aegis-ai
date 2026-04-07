from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.types import JSON
from datetime import datetime

from aegis_ai.db.session import Base


class CognitiveSnapshot(Base):
    __tablename__ = "aegis_cognitive_snapshots"

    tenant = Column(String, nullable=False, index=True)
    snapshot_id = Column(String, primary_key=True)
    brain_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)

    health_score = Column(Float, nullable=False)

    # ✅ Dialect-safe JSON (JSONB in Postgres, JSON in SQLite)
    snapshot_blob = Column(JSON, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
