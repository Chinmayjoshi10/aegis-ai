from gateway.event_gateway import ingest
import pandas as pd
import os

df = pd.read_csv('aegis_ai/data/test_unknown.csv')
res = ingest({'domain':'demo_factory','data': df})
print('keys:', list(res.keys()))
print('semantic_contract:', res.get('semantic_contract'))
print('memory_db exists:', os.path.exists('aegis_memory.db'))
print('baseline_score:', res.get('baseline_score'))
print('risk:', res.get('risk'))
print('escalation:', res.get('escalation'))
