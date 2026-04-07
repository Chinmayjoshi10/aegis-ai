from fastapi import APIRouter, UploadFile, File, HTTPException
from aegis_ai.security.tenant_context import get_current_tenant
from aegis_ai.quarantine.dataset_registry import QuarantineDataset
from aegis_ai.quarantine.schema_contracts import DOMAIN_SCHEMAS
from aegis_ai.db.session import SessionLocal
import os, csv, uuid, shutil

router = APIRouter(prefix="/quarantine", tags=["Quarantine"])

BASE_PATH = "quarantine_storage"

@router.post("/load/{domain}")
async def quarantine_load(domain: str, file: UploadFile = File(...)):
    tenant_id = get_current_tenant()
    if not tenant_id:
        raise HTTPException(401, "Missing tenant context")

    if domain not in DOMAIN_SCHEMAS:
        raise HTTPException(400, "Unknown domain")

    os.makedirs(BASE_PATH, exist_ok=True)
    fname = f"{uuid.uuid4()}.csv"
    fpath = os.path.join(BASE_PATH, fname)

    # Stream file to disk (no RAM blowups)
    with open(fpath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Header-only read for schema guard
    with open(fpath, newline='') as f:
        reader = csv.reader(f)
        headers = set(next(reader))

    expected = DOMAIN_SCHEMAS[domain]
    if not expected.issubset(headers):
        os.remove(fpath)
        raise HTTPException(422, f"Schema mismatch. Expected at least: {expected}")

    # Safe DB session
    with SessionLocal() as db:
        record = QuarantineDataset(
            tenant_id=tenant_id,
            domain=domain,
            file_path=fpath,
            status="pending"
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    return {
        "dataset_id": record.id,
        "status": "pending",
        "message": "Dataset quarantined and schema-validated"
    }
