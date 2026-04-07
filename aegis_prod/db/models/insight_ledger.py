from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    BigInteger,
    Index,
)
from aegis_ai.db.session import Base


class InsightLedger(Base):
    __tablename__ = "insight_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # What kind of truth this was
    primitive = Column(String(32), nullable=False)
    metric = Column(String(128), nullable=False)
    subtype = Column(String(64), nullable=True)

    # Confidence at time of observation
    confidence = Column(Float, nullable=False)

    # Scope (future-proof)
    scope = Column(String(32), default="GLOBAL", nullable=False)

    # Prevent duplicate spam of identical insights
    evidence_hash = Column(String(128), nullable=False)

    # When this insight was observed
    observed_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        Index(
            "idx_insight_lookup",
            "primitive",
            "metric",
            "subtype",
            "observed_at",
        ),
    )
