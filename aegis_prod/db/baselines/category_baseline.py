from sqlalchemy import Column, String
from aegis_ai.db.session import Base

class CategoryBaseline(Base):
    __tablename__ = "category_baselines"

    tenant_id = Column(String, primary_key=True)
    domain = Column(String, primary_key=True)
    category = Column(String, primary_key=True)
