import traceback
try:
    import pandas as pd
    from brains.feature_brain import FeatureBrain
    fb = FeatureBrain()
    df = pd.DataFrame({'a':[1,2,3],'b':[4.0,5.0,6.0]})
    fb.learn_baseline(df)
    print('baselines:', fb.baselines)
    features = fb.extract(df)
    print('features:', features)
except Exception as e:
    traceback.print_exc()
    print('ERROR:', e)
