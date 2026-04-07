from fastapi import APIRouter, HTTPException
from aegis_ai.quarantine.dataset_registry import QuarantineDataset
from aegis_ai.quarantine.drift_guard import DriftGuard
from aegis_ai.security.tenant_context import get_current_tenant
from aegis_ai.db.session import SessionLocal

router = APIRouter(prefix="/quarantine", tags=["Quarantine"])

@router.post("/promote/{dataset_id}")
def promote(dataset_id: str):
    tenant_id = get_current_tenant()
    with SessionLocal() as db:
        dataset = db.query(QuarantineDataset).filter(
            QuarantineDataset.id == dataset_id,
            QuarantineDataset.tenant_id == tenant_id
        ).first()

        if not dataset:
            raise HTTPException(404, "Dataset not found")

        ok, msg = DriftGuard.validate(dataset)
        if not ok:
            raise HTTPException(409, msg)

        dataset.status = "approved"
        db.commit()

        return {"status": "APPROVED", "message": msg}
