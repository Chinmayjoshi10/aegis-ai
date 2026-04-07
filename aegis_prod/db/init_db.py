from aegis_ai.db.session import Base, engine

# Import legacy models.py (Tenant lives here)
import aegis_ai.db.models as legacy_models

# Import baseline models (Phase 1)
from aegis_ai.db.baselines.reality_baseline import RealityBaseline
from aegis_ai.db.baselines.category_baseline import CategoryBaseline
from aegis_ai.db.baselines.semantic_mapping import SemanticMapping

# ✅ THIS IS THE REAL MEMORY MODEL
from aegis_ai.db.models.cognitive_snapshots import CognitiveSnapshot


def init_db():
    print("🔧 Initializing AEGIS database schemas...")
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully.")


if __name__ == "__main__":
    init_db()
