def call_llm(prompt: str) -> str:
    print("LLM PROMPT:\n", prompt)
    return """{
      "facts":[{"entity":"Plant","attribute":"temperature","value":"90","confidence":0.92}],
      "intents":[{"type":"maintenance","payload":{"window":"next_week"},"risk":0.1}],
      "world_state":{"plant_status":"HOT"}
    }"""
