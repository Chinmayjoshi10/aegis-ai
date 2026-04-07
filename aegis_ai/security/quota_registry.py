from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from datetime import datetime
from aegis_ai.db.session import Base

class TenantQuota(Base):
    __tablename__ = "tenant_quotas"

    tenant_id = Column(String, ForeignKey("tenants.id"), primary_key=True)
    day = Column(String, primary_key=True)

    request_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)
