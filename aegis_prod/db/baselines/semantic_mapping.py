import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, UUID

from aegis_ai.db.session import Base

class SemanticMapping(Base):
    __tablename__ = "semantic_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    tenant_id = Column(String, nullable=False, index=True)
    domain = Column(String, nullable=False, index=True)
    original_col = Column(String, nullable=False)
    mapped_col = Column(String, nullable=True)
    method = Column(String, nullable=False)  # "rule" or "llm" or "unmapped"
    status = Column(String, nullable=False)  # "MAPPED" or "UNMAPPED"

    created_at = Column(DateTime, default=datetime.utcnow)
