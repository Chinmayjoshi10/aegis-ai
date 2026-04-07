from collections import defaultdict

class RegimeStabilityBuffer:
    """
    Prevents hallucinated semantic evolution.
    Requires N consecutive identical violations before mutation.
    """

    def __init__(self, N=5):
        self.N = N
        self.buffer = defaultdict(int)

    def record(self, tenant_id: str, signature: str) -> bool:
        key = f"{tenant_id}:{signature}"
        self.buffer[key] += 1
        return self.buffer[key] >= self.N
