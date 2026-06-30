from typing import TypeAlias, cast

import numpy as np
import numpy.typing as npt
import pandas as pd

# =========================
# TYPE ALIASES
# =========================

FloatArray: TypeAlias = npt.NDArray[np.float64]
IntArray: TypeAlias = npt.NDArray[np.int_]


# =========================
# TIME CAUSAL GRAPH
# =========================

class TimeCausalGraph:
    """
    Production-grade time-lag causal graph using lagged correlation + filtering.
    """

    def __init__(
        self,
        lag: int = 1,
        min_score: float = 0.05,
        min_samples: int = 10,
    ):
        self.lag = lag
        self.min_score = min_score
        self.min_samples = min_samples

        self._scores: dict[str, float] = {}
        self._edges: dict[tuple[str, str], float] = {}

    def with_time_lag(self, df: pd.DataFrame) -> "TimeCausalGraph":

        if df is None or df.empty or df.shape[1] < 2:
            self._scores = {}
            self._edges = {}
            return self

        df = self._prepare(df)

        if df.empty or len(df) <= self.lag:
            self._scores = {}
            self._edges = {}
            return self

        cols = list(df.columns)

        scores: dict[str, float] = {}
        edges: dict[tuple[str, str], float] = {}

        for src in cols:
            source = cast(
                FloatArray,
                np.asarray(df[src].to_numpy(copy=False), dtype=np.float64),
            )

            source_lag = source[:-self.lag]

            if (
                source_lag.size < self.min_samples
                or float(np.std(source_lag)) < 1e-9
            ):
                scores[src] = 0.0
                continue

            influence = 0.0
            valid_edges = 0

            for tgt in cols:
                if src == tgt:
                    continue

                target = cast(
                    FloatArray,
                    np.asarray(df[tgt].to_numpy(copy=False), dtype=np.float64),
                )

                target_current = target[self.lag:]

                if (
                    target_current.size < self.min_samples
                    or len(source_lag) != len(target_current)
                    or float(np.std(target_current)) < 1e-9
                ):
                    continue

                corr = np.corrcoef(source_lag, target_current)[0, 1]

                if not np.isfinite(corr):
                    continue

                score = abs(float(corr))

                # 🔥 FILTER WEAK SIGNALS
                if score < self.min_score:
                    continue

                edges[(src, tgt)] = round(score, 4)

                influence += score
                valid_edges += 1

            scores[src] = round(influence / valid_edges, 4) if valid_edges else 0.0

        self._scores = scores
        self._edges = edges
        return self

    def top_drivers(self, limit: int = 3) -> list[tuple[str, float]]:
        ranked = sorted(
            self._scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[:limit]

    def top_edges(self, limit: int = 5) -> list[tuple[tuple[str, str], float]]:
        ranked = sorted(
            self._edges.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[:limit]

    # -------------------------
    # INTERNAL
    # -------------------------

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df = df.select_dtypes(include=[np.number])

        if df.empty:
            return df

        # F-10: Use pairwise deletion instead of zero-fill.
        # fillna(0) creates artificial downward spikes that corrupt
        # lagged correlations. dropna() is statistically honest.
        df = df.dropna()

        if df.empty:
            return df

        # normalize
        df = (df - df.mean()) / (df.std() + 1e-9)

        return df


# =========================
# TRANSFER ENTROPY ENGINE
# =========================

class TransferEntropyEngine:
    """
    Robust Transfer Entropy approximation using lagged mutual information.
    """

    def __init__(
        self,
        lag: int = 1,
        bins: int = 10,
        min_score: float = 0.01,
    ):
        self.lag = lag
        self.bins = bins
        self.min_score = min_score

    def compute(self, df: pd.DataFrame | None) -> dict[tuple[str, str], float]:

        if df is None or df.empty or df.shape[1] < 2:
            return {}

        df = self._prepare(df)

        cols = list(df.columns)
        results: dict[tuple[str, str], float] = {}

        for i in range(len(cols)):
            for j in range(len(cols)):
                if i == j:
                    continue

                src = cols[i]
                tgt = cols[j]

                source = cast(pd.Series, df[src])
                target = cast(pd.Series, df[tgt])

                score = self._transfer_score(source, target)

                if score >= self.min_score:
                    results[(src, tgt)] = round(score, 4)

        return results

    # -------------------------
    # CORE LOGIC
    # -------------------------

    def _transfer_score(self, source: pd.Series, target: pd.Series) -> float:
        try:
            x = cast(FloatArray, source.to_numpy(dtype=np.float64, copy=False))
            y = cast(FloatArray, target.to_numpy(dtype=np.float64, copy=False))

            if len(x) <= self.lag or len(y) <= self.lag:
                return 0.0

            x_lag = x[:-self.lag]
            y_current = y[self.lag:]

            if len(x_lag) != len(y_current):
                return 0.0

            if (
                float(np.std(x_lag)) < 1e-6
                or float(np.std(y_current)) < 1e-6
            ):
                return 0.0

            x_bins = self._safe_discretize(x_lag)
            y_bins = self._safe_discretize(y_current)

            mi = self._mutual_information(x_bins, y_bins)

            return self._normalize_score(mi)

        except Exception:
            return 0.0

    # -------------------------
    # HELPERS
    # -------------------------

    def _safe_discretize(self, arr: FloatArray) -> IntArray:
        try:
            if float(np.std(arr)) < 1e-6:
                return np.zeros_like(arr, dtype=np.int_)

            bins = np.linspace(np.min(arr), np.max(arr), self.bins)
            return np.digitize(arr, bins).astype(np.int_, copy=False)

        except Exception:
            return np.zeros_like(arr, dtype=np.int_)

    def _mutual_information(self, x: IntArray, y: IntArray) -> float:

        joint_xy = np.histogram2d(x, y, bins=self.bins)[0]

        if np.sum(joint_xy) == 0:
            return 0.0

        p_xy = joint_xy / np.sum(joint_xy)

        p_x = np.sum(p_xy, axis=1)
        p_y = np.sum(p_xy, axis=0)

        mi = 0.0

        for i in range(len(p_x)):
            for j in range(len(p_y)):
                if p_xy[i, j] > 0 and p_x[i] > 0 and p_y[j] > 0:
                    mi += p_xy[i, j] * np.log(
                        p_xy[i, j] / (p_x[i] * p_y[j])
                    )

        return float(mi)

    def _normalize_score(self, mi: float) -> float:
        return float(mi / (1 + mi))

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df = df.select_dtypes(include=[np.number])

        if df.empty:
            return df

        # F-10: Pairwise deletion — same fix as TimeCausalGraph
        df = df.dropna()

        if df.empty:
            return df

        df = (df - df.mean()) / (df.std() + 1e-9)

        return df