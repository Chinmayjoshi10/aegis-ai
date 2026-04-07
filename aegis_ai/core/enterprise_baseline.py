class EnterpriseBaseline:
    """
    Stores the healthy equilibrium reference frame of an enterprise.
    This is learned during Phase-6 baseline training.
    """

    def __init__(self):
        self.nominal = {
            "ops_fatigue": 300,
            "hr_burnout": 5,
            "sales_leakage": 0.08,
            "logistics_blockage": 4,
            "finance_fragility": 1.0,
            "runway_days": 60
        }

    def get(self):
        return self.nominal
