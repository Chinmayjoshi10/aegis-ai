import pandas as pd
from aegis_ai.llm.ollama_provider import OllamaProvider
print(OllamaProvider("llama3").generate("Say: AEGIS cognition online"))


data = pd.DataFrame({
    "furnace_temp": [72,81,94,101],
    "co2_ppm": [410,445,480,550],
    "power_kw": [1200,1180,1100,980]
})

prompt = f"""
You are an industrial telemetry classifier.

For each column name ONLY (ignore the values):

Columns:
furnace_temp
co2_ppm
power_kw

Return STRICT JSON in this EXACT format:

{{
 "furnace_temp": {{"meaning":"","unit":"","risk":""}},
 "co2_ppm": {{"meaning":"","unit":"","risk":""}},
 "power_kw": {{"meaning":"","unit":"","risk":""}}
}}

Be extremely concise.
"""


llm = OllamaProvider(model="phi-3:mini")

print(llm.generate(prompt, timeout=60))
