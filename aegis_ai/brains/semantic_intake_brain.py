import json
import requests
from typing import Dict, List


class SemanticIntakeBrain:
    """
    Semantic LLM is used ONLY to interpret column NAMES.
    It NEVER sees data values.
    It NEVER produces numbers.
    """

    @staticmethod
    def _is_valid_column(col: str) -> bool:
        c = col.strip().lower()
        return not (
            c.startswith("unnamed")
            or c in {"id", "idx", "index"}
        )

    def _llm_classify_columns(self, domain: str, columns: List[str]) -> List[Dict]:
        prompt = f"""
You are classifying column NAMES only.
You do NOT see data values.
You must NOT infer numeric values or metrics.

Domain: {domain}

Column names:
{json.dumps(columns, indent=2)}

For each column, return:
- column
- semantic_role (PRICING, DEMAND, INVENTORY, COST, QUALITY, TIME, IDENTIFIER, OTHER)
- confidence (0.0 - 1.0)

STRICT JSON ONLY.

Format:
[
  {{
    "column": "...",
    "semantic_role": "...",
    "confidence": 0.0
  }}
]
"""

        try:
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3",
                    "prompt": prompt,
                    "stream": False
                },
                timeout=20
            )

            text = r.json().get("response", "").strip()
            facts = json.loads(text)

            if not isinstance(facts, list):
                return []

            validated = []
            for f in facts:
                if not all(k in f for k in ("column", "semantic_role", "confidence")):
                    continue

                validated.append({
                    "domain": domain,
                    "column": f["column"].lower(),
                    "semantic_role": f["semantic_role"],
                    "confidence": float(f["confidence"]),
                    "source": "LLM_COLUMN_SEMANTICS"
                })

            return validated

        except Exception:
            return []

    def run(self, state: Dict) -> Dict:
        raw_data = state.get("raw_data", {})
        semantic_facts: List[Dict] = []

        for domain, df in raw_data.items():
            clean_columns = [
                c for c in df.columns
                if self._is_valid_column(c)
            ]

            llm_facts = self._llm_classify_columns(domain, clean_columns)
            semantic_facts.extend(llm_facts)

        state["semantic_facts"] = semantic_facts
        state["semantic_facts_authority"] = "COLUMN_NAME_ONLY"

        return state
