TENANT_REGISTRY = {
    # Local-dev / bootstrap keys (used when DB has not been seeded yet).
    # NOTE: `TenantMiddleware` will ONLY allow keys present here.
    "tenant_alpha": {
        "id": "tenant_alpha",
        "plan": "enterprise",
        "daily_quota": 1_000_000,
    },
    "shadowcorp-key": {
        "id": "shadowcorp",
        "plan": "enterprise",
        "daily_quota": 1_000_000,
    },
}
