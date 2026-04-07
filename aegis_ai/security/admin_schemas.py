from pydantic import BaseModel

class TenantCreateRequest(BaseModel):
    name: str
    plan: str = "free"

class APIKeyResponse(BaseModel):
    api_key: str
    tenant_id: str
