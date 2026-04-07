from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from aegis_ai.db.session import SessionLocal
from aegis_ai.db.models import Tenant
from aegis_ai.security.api_key_manager import APIKey
from aegis_ai.security.admin_schemas import TenantCreateRequest, APIKeyResponse

router = APIRouter(prefix="/admin", tags=["Tenant Admin"])

@router.post("/create-tenant")
def create_tenant(req: TenantCreateRequest):
    db: Session = SessionLocal()
    if db.query(Tenant).filter(Tenant.id == req.name).first():
        raise HTTPException(400, "Tenant already exists")

    tenant = Tenant(id=req.name, plan=req.plan)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant

@router.post("/issue-key", response_model=APIKeyResponse)
def issue_key(tenant_id: str):
    db: Session = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    key = APIKey(tenant_id=tenant.id)
    db.add(key)
    db.commit()
    db.refresh(key)

    return APIKeyResponse(api_key=key.id, tenant_id=tenant.id)  # type: ignore
