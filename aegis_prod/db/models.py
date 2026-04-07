from sqlalchemy import Column, String, Integer
from aegis_ai.db.session import Base

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)
    plan = Column(String, default="free")
    daily_quota = Column(Integer, default=100)
    api_key = Column(String, nullable=True)
    __all__ = ["Tenant"]
