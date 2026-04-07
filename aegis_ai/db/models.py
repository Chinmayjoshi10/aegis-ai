from __future__ import annotations

from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from aegis_ai.db.session import Base

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    plan: Mapped[str] = mapped_column(String, default="free")
    daily_quota: Mapped[int] = mapped_column(Integer, default=100)
    api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    __all__ = ["Tenant"]
