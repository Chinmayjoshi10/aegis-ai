
import joblib, os

class BaselineModelStore:
    """
    Persists baseline ML models per tenant.
    """

    def __init__(self, base_path="baseline_models"):
        os.makedirs(base_path, exist_ok=True)
        self.base_path = base_path

    def _path(self, tenant):
        return os.path.join(self.base_path, f"{tenant}.joblib")

    def save(self, tenant, model):
        joblib.dump(model, self._path(tenant))

    def load(self, tenant):
        path = self._path(tenant)
        return joblib.load(path) if os.path.exists(path) else None
