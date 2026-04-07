from __future__ import annotations

import secrets
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from aegis_ai.db.session import Base

class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: secrets.token_hex(24))
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
