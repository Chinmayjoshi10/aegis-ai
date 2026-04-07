import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Boolean, UUID

from aegis_ai.db.session import Base

class DriftHistory(Base):
    __tablename__ = "drift_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    tenant_id = Column(String, nullable=False, index=True)
    domain = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    column_name = Column(String, nullable=False, index=True)

    baseline_date = Column(DateTime)
    current_date = Column(DateTime, default=datetime.utcnow)

    drift_score = Column(Float)
    drift_type = Column(String)   # scale_shift, distribution_shift, missing_shift
    alert = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
