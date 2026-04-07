class TransferEntropyEngine:
    """Simple transfer entropy stub returning empty scores."""

    def compute(self, df):
        # Return an empty dict so callers can safely use max(...)
        return {}
