import redis
from aegis_ai.security.rate_limiter import PLAN_LIMITS

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

class RedisRateGate:
    @staticmethod
    def check_minute(tenant_id: str, plan: str):
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
        key = f"rl:{tenant_id}"

        count = r.incr(key)
        if count == 1:
            r.expire(key, 60)

        if count > limits["per_minute"]:
            raise Exception("Per-minute rate limit exceeded")
