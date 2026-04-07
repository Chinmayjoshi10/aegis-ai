import traceback
from brains.feature_brain import FeatureBrain
import pandas as pd

errors = []

try:
    fb = FeatureBrain()
    try:
        fb.learn_baseline([1,2,3])
        errors.append('learn_baseline did not raise for non-DataFrame')
    except TypeError:
        pass
    try:
        fb.extract([1,2,3])
        errors.append('extract did not raise for non-DataFrame')
    except TypeError:
        pass
    df = pd.DataFrame({'x':[5]})
    fb.learn_baseline(df)
    features = fb.extract(df)
    if features.get('x_z') != 0.0:
        errors.append('expected x_z == 0.0, got %r' % features.get('x_z'))
except Exception:
    traceback.print_exc()
    raise

if errors:
    print('FAILED:')
    for e in errors:
        print(' -', e)
    raise SystemExit(1)
else:
    print('All checks passed')
