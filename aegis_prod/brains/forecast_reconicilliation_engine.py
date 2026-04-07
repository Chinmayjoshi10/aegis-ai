import numpy as np

class ForecastReconciliationEngine:
    def reconcile(self, forecasts, hierarchy):
        reconciled = {k: np.array(v) for k,v in forecasts.items()}
        for parent, children in hierarchy.items():
            if parent not in reconciled: continue
            total = sum(reconciled[c] for c in children if c in reconciled)
            delta = reconciled[parent] - total
            adjust = delta / len(children)
            for c in children:
                reconciled[c] += adjust
        return {k:v.tolist() for k,v in reconciled.items()}
