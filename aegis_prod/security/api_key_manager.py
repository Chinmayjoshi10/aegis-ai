import secrets
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, DateTime
from aegis_ai.db.session import Base

class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(String, primary_key=True, default=lambda: secrets.token_hex(24))
    tenant_id = Column(String, ForeignKey("tenants.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
