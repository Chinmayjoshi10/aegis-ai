import pandas as pd
import hashlib

def compute_schema_hash(csv_path):
    sample = pd.read_csv(csv_path, nrows=1)
    cols = ",".join(sorted(sample.columns))
    return hashlib.sha256(cols.encode()).hexdigest()

def compute_stats(csv_path):
    df = pd.read_csv(csv_path, usecols=["revenue"], nrows=1000)
    return float(df["revenue"].mean()), float(df["revenue"].std())
