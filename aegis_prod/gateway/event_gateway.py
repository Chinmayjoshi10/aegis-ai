from aegis_ai.memory.shadow_baseline_store import ShadowBaselineStore
from aegis_ai.core.canonical_kernel import build_canonical_kernel

_shadow_store = ShadowBaselineStore()


def ingest(state: dict):
    """
    The ONLY legal entry point into the AEGIS kernel.

    Responsibilities:
    - Persist immutable shadow baseline
    - Invoke canonical deterministic kernel
    - No async
    - No API dependency
    - No global state mutation
    """

    if not isinstance(state, dict):
        raise TypeError("State must be a dictionary")

    tenant = state.get("domain") or state.get("tenant") or "default"

    # Persist immutable raw truth (only if present)
    if "data" in state:
        _shadow_store.persist(tenant, state["data"])

    # Build canonical kernel
    kernel = build_canonical_kernel()

    # Run synchronously
    return kernel.run(state)