import requests
import json

url = "http://127.0.0.1:8011/api/analyze/marketing"
file_path = "marketing_campaign_dataset.csv"

print(f"Submitting {file_path} to API...")
r = requests.post(
    url,
    headers={"X-API-Key": "shadowcorp-key"},
    files={"file": open(file_path, "rb")}
)

try:
    d = r.json()
    with open("eval_output.json", "w") as f:
        json.dump(d, f, indent=2)
        
    print("\n=== STATE ===")
    print(d.get("state"))
    print(d.get("headline"))
        
    print("\n=== NARRATION ===")
    print(d.get("narration", "No narration"))
    
    print("\n=== CHATBOT TEST ===")
    chat_r = requests.post(
        "http://127.0.0.1:8011/api/chat",
        json={"question": "What is the root cause?", "analysis": d}
    )
    print(chat_r.json())
    
except Exception as e:
    print("API returned non-JSON or failed:", r.text)
    print(e)
