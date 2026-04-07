import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, UUID

from aegis_ai.db.session import Base

class RealityBaseline(Base):
    __tablename__ = "reality_baselines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    tenant_id = Column(String, nullable=False, index=True)
    domain = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    column_name = Column(String, nullable=False, index=True)

    mean = Column(Float)
    median = Column(Float)
    std = Column(Float)
    min = Column(Float)
    max = Column(Float)

    null_ratio = Column(Float)
    zero_ratio = Column(Float)
    outlier_ratio = Column(Float)

    upload_date = Column(DateTime, default=datetime.utcnow, index=True)
