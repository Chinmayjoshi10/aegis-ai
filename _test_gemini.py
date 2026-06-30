"""Quick Gemini API test with flash-lite model."""
from dotenv import load_dotenv
load_dotenv(".env", override=True)

from aegis_ai.llm.gemini_provider import GeminiProvider

# Try flash-lite which has separate quota
p = GeminiProvider(model="gemini-2.0-flash-lite")
print(f"Model: {p.model}")

try:
    result = p.generate("Say hello in one word.")
    print(f"Response: {result}")
    print("SUCCESS - Gemini API is working!")
except Exception as e:
    print(f"FAILED with flash-lite: {e}")
    
    # Try gemini-1.5-flash as fallback
    print("\nTrying gemini-1.5-flash...")
    p2 = GeminiProvider(model="gemini-1.5-flash")
    try:
        result = p2.generate("Say hello in one word.")
        print(f"Response: {result}")
        print("SUCCESS with gemini-1.5-flash!")
    except Exception as e2:
        print(f"FAILED with 1.5-flash too: {e2}")
