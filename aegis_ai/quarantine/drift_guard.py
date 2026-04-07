from aegis_ai.quarantine.dataset_signatures import compute_schema_hash, compute_stats
from aegis_ai.quarantine.drift_registry import DriftBaseline
from aegis_ai.db.session import SessionLocal

MAX_DRIFT = 0.20  # 20%

class DriftGuard:

    @staticmethod
    def validate(dataset):
        schema_hash = compute_schema_hash(dataset.file_path)
        mean, std = compute_stats(dataset.file_path)

        with SessionLocal() as db:
            base = db.query(DriftBaseline).filter(
                DriftBaseline.tenant_id == dataset.tenant_id,
                DriftBaseline.domain == dataset.domain
            ).first()

            if not base:
                base = DriftBaseline(
                    tenant_id=dataset.tenant_id,
                    domain=dataset.domain,
                    schema_hash=schema_hash,
                    revenue_mean=mean,
                    revenue_std=std
                )
                db.add(base)
                db.commit()
                return True, "Baseline created"

            # Strict schema drift
            if base.schema_hash != schema_hash:
                return False, "SCHEMA DRIFT"

            # Fuzzy statistical drift
            if abs(mean - base.revenue_mean) / base.revenue_mean > MAX_DRIFT:
                return False, "STATISTICAL DRIFT"

            return True, "Stable"
