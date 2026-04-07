from datetime import datetime
from sqlalchemy import text
from aegis_ai.db.models import Tenant     



PLAN_LIMITS = {
    "free": {"per_minute": 30, "per_day": 300},
    "pro": {"per_minute": 300, "per_day": 5000},
    "enterprise": {"per_minute": 2000, "per_day": 50000}
}

class RateLimiter:

    @staticmethod
    def atomic_increment_daily(db, tenant: Tenant):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        limits = PLAN_LIMITS.get(tenant.plan, PLAN_LIMITS["free"])

        db.execute(text("""
            INSERT INTO tenant_quotas (tenant_id, day, request_count)
            VALUES (:tid, :day, 0)
            ON CONFLICT (tenant_id, day) DO NOTHING
        """), {"tid": tenant.id, "day": today})

        result = db.execute(text("""
            UPDATE tenant_quotas
            SET request_count = request_count + 1
            WHERE tenant_id = :tid AND day = :day
            RETURNING request_count
        """), {"tid": tenant.id, "day": today}).fetchone()

        db.commit()

        if result and result[0] > limits["per_day"]:
            raise Exception("Daily quota exceeded")
