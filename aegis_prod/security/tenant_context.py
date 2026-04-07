from contextvars import ContextVar
from typing import Optional

_current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)

def set_current_tenant(tenant_id: str):
    _current_tenant.set(tenant_id)

def get_current_tenant() -> Optional[str]:
    return _current_tenant.get()

def clear_current_tenant():
    _current_tenant.set(None)
