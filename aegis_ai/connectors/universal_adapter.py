import time
import re
from aegis_ai.spine.domain_injector import DomainInjector
from aegis_ai.spine.lineage_audit import LineageAudit


class UniversalAdapter:
    """
    Universal Enterprise Nervous Interface (U-ENI)
    Converts ANY messy company data into clean CES impulses.
    """

    VALID_DOMAINS = {"sales", "ops", "logistics", "finance", "hr"}

    # ── Unit standardization library
    UNIT_LIBRARY = {
        "usd": 1.0,
        "$": 1.0,
        "inr": 0.012,   # INR → USD approx
        "eur": 1.1,
        "minutes": 1/60,
        "hours": 1.0,
        "days": 24.0,
        "%": 0.01
    }

    def __init__(self):
        self.injector = DomainInjector()
        self.audit = LineageAudit()

    # ─────────────────────────────────────────────
    # Robust numeric scrubber
    # ─────────────────────────────────────────────
    def _clean_number(self, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)

        s = str(v).lower().strip()

        # Remove commas
        s = s.replace(",", "")

        # Scientific notation
        try:
            return float(s)
        except:
            pass

        # Currency / percentage
        match = re.findall(r"([-+]?[0-9]*\.?[0-9]+)", s)
        if not match:
            return None

        return float(match[0])

    # ─────────────────────────────────────────────
    # Unit scaling
    # ─────────────────────────────────────────────
    def _apply_units(self, value, raw_string):
        raw = str(raw_string).lower()
        for unit, scale in self.UNIT_LIBRARY.items():
            if unit in raw:
                return value * scale
        return value

    # ─────────────────────────────────────────────
    # Create CES impulse
    # ─────────────────────────────────────────────
    def ces(self, domain, metric, value, source):
        return {
            "domain": domain,
            "metric": metric,
            "value": float(value),
            "timestamp": time.time(),
            "source": source
        }

    # ─────────────────────────────────────────────
    # MULTI-INJECTION BATCH NORMALIZER
    # mapping → raw_field : [(domain,metric),(domain,metric)...]
    # ─────────────────────────────────────────────
    def batch(self, rows: list, mapping: dict, source: str):
        signals = []

        for r in rows:
            for raw_key, targets in mapping.items():

                if raw_key not in r:
                    continue

                raw_val = r[raw_key]
                clean = self._clean_number(raw_val)

                if clean is None:
                    # semantic noise logging
                    self.audit.log(r, [], source, "SEMANTIC_NOISE")
                    continue

                clean = self._apply_units(clean, raw_val)

                for domain, metric in targets:
                    if domain not in self.VALID_DOMAINS:
                        continue
                    signals.append(self.ces(domain, metric, clean, source))

        return signals

    # ─────────────────────────────────────────────
    # DIRECT INJECTION INTO ORGANISM
    # ─────────────────────────────────────────────
    def inject(self, physics_state, rows, mapping, source, confidence=1.0):
        ces_packets = self.batch(rows, mapping, source)
        self.injector.inject(physics_state, ces_packets, confidence)
