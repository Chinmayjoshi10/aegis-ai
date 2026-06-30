import sys
import json
import asyncio
import os

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from aegis_ai.core.orchestrator import run_aegis
from aegis_ai.core.narration import generate_narration

async def main():
    csv_path = "c:\\Users\\chinm\\aegis_ai\\marketing_campaign_dataset.csv"
    print(f"Running pipeline on {csv_path}...")
    
    result = await run_aegis(
        csv_path=csv_path,
        tenant_id="test",
        domain="marketing"
    )
    
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
