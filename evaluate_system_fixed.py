import sys
import json
import asyncio
import os

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from aegis_ai.core.decision_pipeline import DecisionPipeline
from aegis_ai.core.narration import generate_narration
import pandas as pd

async def main():
    csv_path = "c:\\Users\\chinm\\aegis_ai\\marketing_campaign_dataset.csv"
    print(f"Running pipeline on {csv_path}...")
    
    df = pd.read_csv(csv_path)
    
    pipeline = DecisionPipeline(tenant_id="test", domain="marketing")
    result = await pipeline.run(df)
    
    print("\n" + "="*50)
    print("=== JSON OUTPUT ===")
    print("="*50)
    print(json.dumps(result, indent=2))
    
    narration = generate_narration(result)
    
    print("\n" + "="*50)
    print("=== NARRATION OUTPUT ===")
    print("="*50)
    print(narration)

if __name__ == "__main__":
    asyncio.run(main())
