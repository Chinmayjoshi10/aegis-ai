ACTION_CATALOG = {
    "increase_ops_capacity": {
        "domain": "ops",
        "base_effect": {"throughput": +0.05},   # at low risk
        "max_effect":  {"throughput": +0.40},   # at extreme risk
        "cost_domain": "finance",
        "cost_effect": {"burn_rate": +0.05},
        "cooldown_days": 14
    },
    "hire_critical_roles": {
        "domain": "hr",
        "base_effect": {"hiring_velocity": +0.05},
        "max_effect":  {"hiring_velocity": +0.35},
        "cost_domain": "finance",
        "cost_effect": {"burn_rate": +0.07},
        "cooldown_days": 21
    },
    "throttle_sales_campaigns": {
        "domain": "sales",
        "base_effect": {"flow_rate": -0.05},
        "max_effect":  {"flow_rate": -0.40},
        "cooldown_days": 7
    },
    "prioritize_logistics_clearance": {
        "domain": "logistics",
        "base_effect": {"blockage": -0.10},
        "max_effect":  {"blockage": -0.50},
        "cooldown_days": 10
    },
    "freeze_nonessential_spend": {
        "domain": "finance",
        "base_effect": {"burn_rate": -0.05},
        "max_effect":  {"burn_rate": -0.30},
        "cooldown_days": 14
    },
}
