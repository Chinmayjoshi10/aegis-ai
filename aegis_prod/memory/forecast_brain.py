import numpy as np
from statsmodels.tsa.api import VAR

try:
    from arch import arch_model
except ImportError:
    arch_model = None

from aegis_ai.memory.shadow_baseline_store import ShadowBaselineStore
from aegis_ai.brains.semantic_grouping_engine import SemanticGroupingEngine
from aegis_ai.brains.forecast_reconicilliation_engine import ForecastReconciliationEngine
from aegis_ai.memory.forecast_hierarchy import FORECAST_HIERARCHY


class ForecastBrainV4:
    """
    Forecast Layer (Non-Canonical)

    Characteristics:
    - Time-series aware
    - May use stochastic simulation
    - Optional ARCH volatility modeling
    - Must not crash if optional deps missing
    """

    def __init__(self, tenant, seed: int = 42):
        self.tenant = tenant
        self.shadow = ShadowBaselineStore()
        self.grouping = SemanticGroupingEngine(tenant)
        self.reconciler = ForecastReconciliationEngine()
        self.rng = np.random.default_rng(seed)

    # ---------------------------------------------------------
    # Automatic Lag Selection
    # ---------------------------------------------------------
    def _auto_lag(self, df):
        best_lag = 1
        best_aic = float("inf")

        for lag in [2, 5, 10, 20, 30]:
            try:
                model = VAR(df).fit(lag)
                if model.aic < best_aic:
                    best_aic = model.aic
                    best_lag = lag
            except Exception:
                continue

        return best_lag

    # ---------------------------------------------------------
    # Main Forecast Execution
    # ---------------------------------------------------------
    def run(self, horizon=7):

        raw = self.shadow.load(self.tenant).select_dtypes(include="number")
        groups = self.grouping.build_groups(raw)

        forecasts = {}

        for group_name, cols in groups.items():

            df = raw[cols].dropna()

            if len(df) < 10:
                continue

            lag = self._auto_lag(df)

            model = VAR(df).fit(lag)
            base_forecast = model.forecast(df.values[-lag:], horizon)

            for i, col in enumerate(cols):

                resid = model.resid[:, i]

                # -------------------------------------------------
                # Volatility Modeling (Optional ARCH)
                # -------------------------------------------------
                if arch_model is not None:
                    try:
                        arch_fit = arch_model(resid, p=1, q=1).fit(disp="off")
                        vol = arch_fit.conditional_volatility.iloc[-1]
                    except Exception:
                        vol = np.std(resid)
                else:
                    # Deterministic fallback
                    vol = np.std(resid)

                # -------------------------------------------------
                # Monte Carlo Simulation (Seeded RNG)
                # -------------------------------------------------
                noise = self.rng.choice(resid, size=(500, horizon))
                sims = base_forecast[:, i] + noise * vol

                forecasts[col] = np.percentile(
                    sims, [5, 50, 95], axis=0
                ).tolist()

        coherent = self.reconciler.reconcile(
            forecasts,
            FORECAST_HIERARCHY,
        )

        return {"enterprise_forecast": coherent}