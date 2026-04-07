from datetime import datetime
from typing import Optional

class AegisClock:
    def __init__(self, fixed_time: Optional[datetime] = None):
        self._fixed = fixed_time

    def now(self) -> datetime:
        return self._fixed or datetime.utcnow()