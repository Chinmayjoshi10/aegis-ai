"""Tenant resolution + scope injection.

Why this exists:
- `BaseHTTPMiddleware` uses Starlette TaskGroups that clone `scope` and can break
  fragile tenant propagation patterns.
- This middleware is ASGI-native and uses `scope` as the *single source of truth*
  for tenant context.

Contract:
- On authenticated requests, inject tenant context into `scope["aegis.tenant"]`.
- Do not use `request.state`, globals, or contextvars.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable, Mapping, MutableMapping, Optional, Sequence

import anyio
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Receive, Scope, Send

from aegis_ai.db.models import Tenant      

from aegis_ai.db.session import SessionLocal
from aegis_ai.security.api_key_manager import APIKey
from aegis_ai.security.tenant_registry import TENANT_REGISTRY


@dataclass(frozen=True)
class TenantContext:
    """Minimal tenant context required at the gateway edge."""

    id: str
    plan: str
    daily_quota: int


def _get_header(scope: Scope, name: bytes) -> Optional[str]:
    """Return decoded header value (case-insensitive), or None."""
    headers = scope.get("headers") or []
    name_l = name.lower()
    for k, v in headers:
        if k.lower() == name_l:
            try:
                return v.decode("latin-1")
            except Exception:
                return None
    return None


async def _send_json(send: Send, status_code: int, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class TenantMiddleware:
    """Authenticate X-API-Key and inject tenant context into ASGI scope."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        public_paths: Sequence[str] = (
            "/",
            "/health",
            "/health/llm",
            "/health/llm/warmup",
            "/ready",
            "/docs",
            "/docs/oauth2-redirect",
            "/openapi.json",
            "/redoc",
            "/_auth_probe",
        ),
    ) -> None:
        self.app = app
        self.public_paths = tuple(public_paths)

    def _is_public(self, scope: Scope) -> bool:
        if scope.get("type") != "http":
            return True

        method = (scope.get("method") or "").upper()
        if method == "OPTIONS":
            return True

        path = scope.get("path") or ""
        # Prefix match for Swagger UI static subpaths.
        if path.startswith("/docs"):
            return True

        return path in self.public_paths

    @staticmethod
    def _resolve_tenant_sync(api_key: str) -> Optional[TenantContext]:
        """Resolve API key to tenant context.

        Resolution order:
        1) Database API key table (production path).
        2) Tenant.api_key column (legacy path).
        3) Static registry bootstrap (local dev / breakglass).
        """

        db: Session = SessionLocal()
        try:
            key_row = db.query(APIKey).filter(APIKey.id == api_key).first()
            if key_row is not None:
                tenant = db.query(Tenant).filter(Tenant.id == key_row.tenant_id).first()
                if tenant is None:
                    return None
                return TenantContext(
                    id=str(tenant.id),
                    plan=str(getattr(tenant, "plan", "free") or "free"),
                    daily_quota=int(getattr(tenant, "daily_quota", 0) or 0),
                )

            # Legacy / transitional support.
            tenant = db.query(Tenant).filter(Tenant.api_key == api_key).first()
            if tenant is not None:
                return TenantContext(
                    id=str(tenant.id),
                    plan=str(getattr(tenant, "plan", "free") or "free"),
                    daily_quota=int(getattr(tenant, "daily_quota", 0) or 0),
                )

        finally:
            db.close()

        # Bootstrap registry fallback (do not bypass auth; only matches known keys).
        reg = TENANT_REGISTRY.get(api_key)
        if reg:
            return TenantContext(
                id=str(reg.get("id")),
                plan=str(reg.get("plan", "free") or "free"),
                daily_quota=int(reg.get("daily_quota", 0) or 0),
            )

        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._is_public(scope):
            await self.app(scope, receive, send)
            return

        api_key = _get_header(scope, b"x-api-key")
        if not api_key:
            await _send_json(send, 401, {"detail": "Missing API key"})
            return

        tenant_ctx = await anyio.to_thread.run_sync(self._resolve_tenant_sync, api_key)
        if tenant_ctx is None:
            await _send_json(send, 401, {"detail": "Invalid API key"})
            return

        # ASGI scope injection is the single source of truth.
        # This survives Starlette scope cloning because the cloned dict retains these keys.
        scope["aegis.tenant"] = asdict(tenant_ctx)
        scope["tenant_id"] = tenant_ctx.id  # compatibility shim
        scope["aegis.api_key"] = api_key

        await self.app(scope, receive, send)
