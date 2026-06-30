import numpy as np
import pandas as pd


def _to_numeric(arr) -> np.ndarray:
    numeric = pd.to_numeric(pd.Series(arr), errors="coerce")
    return np.asarray(numeric, dtype=np.float64)


class TransferEntropyEngine:
    """
    Practical Transfer Entropy approximation using lagged mutual information.
    Deterministic, fast, production-safe.
    """

    def __init__(self, lag: int = 1, bins: int = 10):
        self.lag = lag
        self.bins = bins

    # -------------------------
    # MAIN ENTRY
    # -------------------------

    def compute(self, df: pd.DataFrame):
        """
        Returns:
        {
            (source, target): score
        }
        """

        if df is None or df.empty or df.shape[1] < 2:
            return {}

        df = self._prepare(df)

        cols = df.columns
        results = {}

        for i in range(len(cols)):
            for j in range(len(cols)):
                if i == j:
                    continue

                src = cols[i]
                tgt = cols[j]

                score = self._transfer_score(df[src], df[tgt])

                if score > 0:
                    results[(src, tgt)] = round(score, 4)

        return results

    # -------------------------
    # CORE TRANSFER LOGIC
    # -------------------------

    def _transfer_score(self, source: pd.Series, target: pd.Series) -> float:
        """
        Approximate TE using lagged mutual information
        """

        try:
            x = _to_numeric(source.values)
            y = _to_numeric(target.values)

            if len(x) <= self.lag or len(y) <= self.lag:
                return 0.0

            # lagged alignment
            x_lag = x[:-self.lag]
            y_current = y[self.lag:]

            x_lag = _to_numeric(x_lag)
            y_current = _to_numeric(y_current)

            if x_lag.size == 0 or y_current.size == 0:
                return 0.0

            if np.isnan(x_lag).all() or np.isnan(y_current).all():
                return 0.0

            x_lag = np.nan_to_num(x_lag, nan=0.0)
            y_current = np.nan_to_num(y_current, nan=0.0)

            # discretize
            x_bins = self._discretize(x_lag)
            y_bins = self._discretize(y_current)

            # compute mutual information
            mi = self._mutual_information(x_bins, y_bins)

            return mi

        except Exception:
            return 0.0

    # -------------------------
    # DISCRETIZATION
    # -------------------------

    def _discretize(self, arr):
        try:
            numeric_arr = _to_numeric(arr)

            if numeric_arr.size == 0 or np.isnan(numeric_arr).all():
                return np.asarray([], dtype=np.int64)

            numeric_arr = np.nan_to_num(numeric_arr, nan=0.0)
            bins = np.histogram_bin_edges(numeric_arr, bins=self.bins)
            return np.digitize(numeric_arr, bins)
        except Exception:
            return np.asarray([], dtype=np.int64)

    # -------------------------
    # MUTUAL INFORMATION
    # -------------------------

    def _mutual_information(self, x, y):
        x = _to_numeric(x)
        y = _to_numeric(y)

        if x.size == 0 or y.size == 0:
            return 0.0

        joint_xy = np.histogram2d(x, y, bins=self.bins)[0]
        total = np.sum(joint_xy)

        if total <= 0:
            return 0.0

        # normalize
        p_xy = joint_xy / total

        p_x = np.sum(p_xy, axis=1)
        p_y = np.sum(p_xy, axis=0)

        mi = 0.0

        for i in range(len(p_x)):
            for j in range(len(p_y)):
                if p_xy[i, j] > 0 and p_x[i] > 0 and p_y[j] > 0:
                    mi += p_xy[i, j] * np.log(p_xy[i, j] / (p_x[i] * p_y[j]))

        return float(mi)

    # -------------------------
    # CLEAN INPUT
    # -------------------------

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df = df.apply(pd.to_numeric, errors="coerce")
        df = df.select_dtypes(include=[np.number])

        # fill missing
        df = df.astype(np.float64).fillna(0.0)

        # normalize scale
        df = (df - df.mean()) / (df.std(ddof=0) + 1e-9)

        return df
