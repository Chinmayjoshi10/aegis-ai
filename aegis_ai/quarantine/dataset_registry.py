import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from aegis_ai.db.session import Base

class QuarantineDataset(Base):
    __tablename__ = "quarantine_datasets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String)
    domain = Column(String)
    file_path = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
