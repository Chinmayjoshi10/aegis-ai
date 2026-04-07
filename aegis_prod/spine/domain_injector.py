from aegis_ai.spine.event_store import EventStore


class DomainInjector:
    """
    Non-destructive synaptic injector for AEGIS physics organs.
    Protects physics integrity, limits volatility, and enforces validation.
    """

    PROTECTED_CONSTANTS = {"max_capacity", "min_capacity", "structural_limit"}
    SLEW_LIMIT = 0.50   # 50% per cycle

    def __init__(self):
        self.store = EventStore()

    def inject(self, physics_state, events: list, confidence: float = 1.0):
        for e in events:
            try:
                organ = getattr(physics_state, e["domain"])
                metric = e["metric"]
                value = float(e["value"])

                # 1. Protect core constants
                if metric in self.PROTECTED_CONSTANTS:
                    continue

                current = getattr(organ, metric, None)

                # 2. Slew rate limiter
                if current is not None and current > 0:
                    delta = abs(value - current) / current
                    if delta > self.SLEW_LIMIT and confidence < 0.8:
                        continue  # discard extreme volatility

                # 3. Inject
                setattr(organ, metric, value)

                # 4. Organ internal validation
                if hasattr(organ, "validate"):
                    if not organ.validate():
                        setattr(organ, metric, current)
                        continue

                # 5. Record successful neural impulse
                self.store.write([{
                    "domain": e["domain"],
                    "metric": metric,
                    "value": value
                }], confidence)

            except Exception:
                # Fail-safe: never crash the organism
                continue
