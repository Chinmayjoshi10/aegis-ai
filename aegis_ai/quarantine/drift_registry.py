from sqlalchemy import Column, String, Float, DateTime
from datetime import datetime
from aegis_ai.db.session import Base

class DriftBaseline(Base):
    __tablename__ = "drift_baselines"

    tenant_id = Column(String, primary_key=True)
    domain = Column(String, primary_key=True)

    schema_hash = Column(String)

    revenue_mean = Column(Float, nullable=True)
    revenue_std = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
