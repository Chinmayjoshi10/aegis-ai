from aegis_ai.db.session import Base, engine

# IMPORTANT:
# Import legacy models.py directly (NOT the models/ package)
import aegis_ai.db.models as legacy_models  # contains Tenant

# Import baseline tables (these register themselves)
from aegis_ai.db.baselines.reality_baseline import RealityBaseline
from aegis_ai.db.baselines.category_baseline import CategoryBaseline
from aegis_ai.db.baselines.semantic_mapping import SemanticMapping

# Import new Insight Ledger model
from aegis_ai.db.models.insight_ledger import InsightLedger


def init_db():
    print("🔧 Initializing AEGIS database schemas...")
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully.")


if __name__ == "__main__":
    init_db()
