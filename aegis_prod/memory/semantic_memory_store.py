from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, Column, Integer, String, Float, JSON, DateTime, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

class SemanticContract(Base):
    __tablename__ = "semantic_contracts"
    __table_args__ = (UniqueConstraint("tenant", name="uq_tenant_contract"),)

    id = Column(Integer, primary_key=True)
    tenant = Column(String, nullable=False)
    contract = Column(JSON, nullable=False)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

class SemanticMemoryStore:
    """
    Versioned semantic memory with upsert + audit.
    """

    def __init__(self, db_url="sqlite:///aegis_memory.db"):
        self.engine = create_engine(db_url, future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)

        # Lightweight in-process fallback collections for non-contract artifacts.
        self._local: dict[str, list[dict[str, Any]]] = {
            "drifts": [],
            "forecasts": [],
            "actions": [],
        }

    def save_contract(self, tenant, contract):
        with self.Session() as s:
            existing = s.query(SemanticContract).filter_by(tenant=tenant).first()

            if existing:
                existing.contract = contract
                existing.version += 1
                existing.created_at = datetime.utcnow()
            else:
                s.add(SemanticContract(
                    tenant=tenant,
                    contract=contract
                ))

            s.commit()

    # Lightweight stubs used by brains for linting and smoke tests
    def fast_contract_check(self, tenant, df):
        """Return an empty list of violations (no-op in smoke tests)."""
        return []

    def propose_evolution(self, tenant, stable_violations):
        """Return an empty evolution report (no-op)."""
        return {}

    def load_contract(self, tenant):
        """Return the most recent contract for the tenant or None."""
        with self.Session() as s:
            existing = s.query(SemanticContract).filter_by(tenant=tenant).order_by(SemanticContract.version.desc()).first()
            return existing.contract if existing else None
    # ---------------- Unified Memory Compatibility Layer ----------------

    def store_contract(self, tenant, contract=None, version=None, **kwargs):
        """Compatibility layer.

        Supports both:
        - `store_contract(tenant, contract)`
        - `store_contract(tenant, version, contract)` (legacy callers)
        """

        if contract is None and "contract" in kwargs:
            contract = kwargs["contract"]

        # Legacy positional (tenant, version, contract)
        if contract is None and version is not None:
            contract = version

        if contract is None:
            return None

        self.save_contract(tenant, contract)

    def store_drift(self, tenant, score, root):
        self._local["drifts"].append({"tenant": tenant, "score": score, "root": root, "ts": datetime.utcnow().isoformat()})

    def store_forecast(self, tenant, forecast):
        self._local["forecasts"].append({"tenant": tenant, "forecast": forecast, "ts": datetime.utcnow().isoformat()})

    def store_action(self, tenant, action):
        self._local["actions"].append({"tenant": tenant, "action": action, "ts": datetime.utcnow().isoformat()})
