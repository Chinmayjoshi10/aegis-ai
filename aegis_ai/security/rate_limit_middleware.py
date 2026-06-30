"""Rate limiting middleware.

Implementation notes:
- ASGI-native (no BaseHTTPMiddleware) to avoid TaskGroup scope cloning issues.
- Reads tenant context from `scope["aegis.tenant"]` injected by TenantMiddleware.
- Does not touch request body, so multipart uploads pass through unchanged.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping, MutableMapping, Optional, Sequence

import anyio
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Receive, Scope, Send

from aegis_ai.db.session import SessionLocal


# Keep limits colocated with the enforcement edge. This avoids importing other
# modules that may pull in DB models / registries at import time.
PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free": {"per_minute": 30, "per_day": 300},
    "pro": {"per_minute": 300, "per_day": 5000},
    "enterprise": {"per_minute": 2000, "per_day": 50000},
}


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


class RateLimitMiddleware:
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
        if path.startswith("/docs"):
            return True
        return path in self.public_paths

    @staticmethod
    def _increment_daily_sync(tenant_id: str, plan: str) -> None:
        """DB-backed daily quota increment.

        Expects `tenant_quotas(tenant_id, day, request_count)` to exist.
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

        db: Session = SessionLocal()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO tenant_quotas (tenant_id, day, request_count)
                    VALUES (:tid, :day, 0)
                    ON CONFLICT (tenant_id, day) DO NOTHING
                    """
                ),
                {"tid": tenant_id, "day": today},
            )

            try:
                result = db.execute(
                    text(
                        """
                        UPDATE tenant_quotas
                        SET request_count = request_count + 1
                        WHERE tenant_id = :tid AND day = :day
                        RETURNING request_count
                        """
                    ),
                    {"tid": tenant_id, "day": today},
                ).fetchone()
                db.commit()
                current = int(result[0]) if result else 0
            except Exception:
                # Older SQLite builds may not support RETURNING; fall back to two-step.
                db.execute(
                    text(
                        """
                        UPDATE tenant_quotas
                        SET request_count = request_count + 1
                        WHERE tenant_id = :tid AND day = :day
                        """
                    ),
                    {"tid": tenant_id, "day": today},
                )
                db.commit()
                row = db.execute(
                    text(
                        """
                        SELECT request_count
                        FROM tenant_quotas
                        WHERE tenant_id = :tid AND day = :day
                        """
                    ),
                    {"tid": tenant_id, "day": today},
                ).fetchone()
                current = int(row[0]) if row else 0

            if current > int(limits["per_day"]):
                raise RuntimeError("Daily quota exceeded")
        finally:
            db.close()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._is_public(scope):
            await self.app(scope, receive, send)
            return

        tenant: Optional[MutableMapping[str, Any]] = scope.get("aegis.tenant")  # type: ignore[assignment]
        if not tenant or not tenant.get("id"):
            await _send_json(send, 401, {"detail": "Missing tenant context"})
            return

        tenant_id = str(tenant["id"])
        plan = str(tenant.get("plan") or "free")

        degraded: list[str] = []

        # 1) Per-minute gate (Redis)
        try:
            # Optional dependency: redis. If unavailable, degrade to daily quota only.
            from aegis_ai.security.redis_rate_gate import RedisRateGate

            await anyio.to_thread.run_sync(RedisRateGate.check_minute, tenant_id, plan)
        except ModuleNotFoundError:
            # Production posture: prefer availability while preserving auth.
            # Rate-limit enforcement is degraded when the backend is unavailable.
            degraded.append("minute")
        except Exception as e:
            # If redis is installed, surface backend errors as degraded; only enforce
            # when we can be certain the tenant exceeded limits.
            if e.__class__.__module__.startswith("redis"):
                degraded.append("minute")
                # fall through
            elif "rate limit" in str(e).lower():
                await _send_json(send, 429, {"detail": str(e)})
                return
            else:
                raise

        # 2) Daily quota (DB)
        try:
            await anyio.to_thread.run_sync(self._increment_daily_sync, tenant_id, plan)
        except Exception as e:
            msg = str(e)
            if "quota" in msg.lower() or "exceeded" in msg.lower():
                await _send_json(send, 429, {"detail": msg})
                return
            degraded.append("daily")

        # If degraded, annotate response without changing semantics.
        if degraded:
            async def send_with_header(message: dict) -> None:
                if message.get("type") == "http.response.start":
                    headers = list(message.get("headers") or [])
                    headers.append(
                        (
                            b"x-aegis-ratelimit-degraded",
                            (";".join(degraded)).encode("ascii", errors="ignore"),
                        )
                    )
                    message["headers"] = headers
                await send(message)  # type: ignore[arg-type]

            await self.app(scope, receive, send_with_header)
            return

        await self.app(scope, receive, send)
