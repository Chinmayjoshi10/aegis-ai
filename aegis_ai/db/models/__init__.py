"""Central export for DB models.

NOTE:
- `aegis_ai.db.models` exists both as a *module* (models.py) and a *package*
  (models/). Python will prefer the package, which means attempting to import
  Tenant from `aegis_ai.db.models.tenant` fails (no such module).

To avoid circular imports and ambiguity, we define the missing Tenant model in
this package as a thin re-export.
"""

from sqlalchemy import Column, Integer, String

from aegis_ai.db.session import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True)
    plan = Column(String, default="free")
    daily_quota = Column(Integer, default=100)
    api_key = Column(String, nullable=True)


from aegis_ai.db.models.cognitive_snapshots import CognitiveSnapshot
 
__all__ = [
    "Tenant",
    "CognitiveSnapshot",
]
