import numpy as np

def compute_psi(baseline_series, live_series):
    """Very small PSI-style metric: absolute normalized mean difference.
    This is a lightweight stub for linting/tests.
    """
    try:
        b = np.nanmean(baseline_series)
        l = np.nanmean(live_series)
        return float(abs(b - l))
    except Exception:
        return 0.0
