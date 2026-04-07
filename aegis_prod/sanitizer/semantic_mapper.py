import json
from sqlalchemy.orm import Session

from aegis_ai.llm.ollama_provider import OllamaProvider
from aegis_ai.db.baselines.semantic_mapping import SemanticMapping


# -------------------------------------------------------------------
# CANONICAL FIELD DEFINITIONS
# -------------------------------------------------------------------
# These are schema-level meanings.
# They DO NOT contain numeric logic.
# They are strictly column-name normalization targets.
# -------------------------------------------------------------------

CANONICAL_FIELDS = {

    # ─────────── Identifiers ───────────
    "Transaction ID": ["transaction id", "txn id", "txn_id", "order id"],
    "Customer ID": ["customer id", "cust id", "client id"],

    # ─────────── Timestamp Fields ───────────
    # Multiple canonical timestamp types supported
    "Order_Date": ["order date", "order_date", "purchase date"],
    "Event_Timestamp": ["event time", "timestamp", "event timestamp"],
    "Created_At": ["created at", "created_at"],
    "Posting_Date": ["posting date", "invoice date", "ship date", "delivery date"],

    # ─────────── Attributes ───────────
    "Gender": ["gender", "sex"],
    "Age": ["age", "years"],
    "Product_Category": ["category", "product category", "prod cat"],

    # ─────────── Metrics ───────────
    "Quantity": ["qty", "quantity", "units"],
    "Price_per_Unit": ["unit price", "price per unit", "ppu"],
    "Total_Amount": ["total", "total amount", "revenue", "sales"],
}


# -------------------------------------------------------------------
# Deterministic Timestamp Field Registry
# This is what ingestion layer will check.
# -------------------------------------------------------------------

TIMESTAMP_FIELDS = {
    "Order_Date",
    "Event_Timestamp",
    "Created_At",
    "Posting_Date",
}


# -------------------------------------------------------------------
# COLUMN HYGIENE — HARD GUARANTEE
# -------------------------------------------------------------------

def _is_valid_column(col: str) -> bool:
    """
    Columns that must NEVER enter semantic, reality, drift, or quality layers.
    This makes the system safe for arbitrary CSVs.
    """
    c = col.strip().lower()
    return not (
        c.startswith("unnamed")
        or c in {"id", "idx", "index"}
    )


# -------------------------------------------------------------------
# SEMANTIC MAPPER
# -------------------------------------------------------------------

class SemanticMapper:
    """
    Schema-level semantic normalization.

    CONTRACT (NON-NEGOTIABLE):
    - Operates ONLY on column names
    - NEVER sees data values
    - NEVER invents numeric information
    - LLM is best-effort fallback
    - Deterministic rule mapping always runs first
    """

    def __init__(
        self,
        session: Session | None = None,
        model: str | None = None,
        *,
        ollama_timeout_s: int | None = None,
    ):
        self.session = session
        self.llm = OllamaProvider(model=model)
        self.ollama_timeout_s = int(ollama_timeout_s or 8)

    # ----------------------------------------------------------------
    # RULE-BASED MAPPING (PRIMARY)
    # ----------------------------------------------------------------
    def _rule_map(self, col: str) -> str | None:
        col_norm = col.strip().lower()

        for canon, variants in CANONICAL_FIELDS.items():
            if col_norm == canon.lower():
                return canon
            for v in variants:
                if v in col_norm:
                    return canon
        return None

    # ----------------------------------------------------------------
    # LLM FALLBACK — COLUMN NAMES ONLY
    # ----------------------------------------------------------------
    def _llm_suggest(self, columns: list[str]) -> dict:
        """
        LLM MUST ONLY see column names.
        It MUST NOT infer values or statistics.
        """

        prompt = f"""
You are a semantic schema mapper for an enterprise system.

Map these column NAMES to the best match from this canonical list:
{list(CANONICAL_FIELDS.keys())}

Rules:
- You ONLY see column names
- Do NOT invent values
- If unsure, return the original column
- Return JSON only

Columns:
{columns}
"""

        try:
            raw = self.llm.generate(prompt, timeout=self.ollama_timeout_s)
        except Exception:
            # LLM failure should never break ingestion
            return {col: col for col in columns}

        try:
            mapping = json.loads(raw)
            if isinstance(mapping, dict):
                return mapping
        except Exception:
            pass

        # Fallback safe behavior
        return {col: col for col in columns}

    # ----------------------------------------------------------------
    # MAIN ENTRY
    # ----------------------------------------------------------------
    def map_columns(self, df, tenant: str, domain: str):
        """
        Returns:
        - cleaned + renamed DataFrame
        - semantic mapping dict {original_col -> mapped_col}
        """

        # ------------------------------------------------------------
        # STEP 0 — HARD DROP JUNK COLUMNS
        # ------------------------------------------------------------
        valid_cols = [c for c in df.columns if _is_valid_column(c)]
        df = df[valid_cols]

        original_cols = list(df.columns)
        mapped: dict[str, str] = {}
        unmapped: list[str] = []

        # ------------------------------------------------------------
        # STEP 1 — RULE-BASED MAPPING
        # ------------------------------------------------------------
        for col in original_cols:
            canon = self._rule_map(col)
            if canon:
                mapped[col] = canon

                if self.session:
                    self.session.add(
                        SemanticMapping(
                            tenant_id=tenant,
                            domain=domain,
                            original_col=col,
                            mapped_col=canon,
                            method="rule",
                            status="MAPPED",
                        )
                    )
            else:
                unmapped.append(col)

        # ------------------------------------------------------------
        # STEP 2 — LLM FALLBACK (UNMAPPED ONLY)
        # ------------------------------------------------------------
        if unmapped:
            llm_map = self._llm_suggest(unmapped)

            for col in unmapped:
                suggested = llm_map.get(col, col)

                if suggested in CANONICAL_FIELDS:
                    mapped[col] = suggested
                    method = "llm"
                    status = "MAPPED"
                else:
                    mapped[col] = col
                    method = "llm"
                    status = "UNMAPPED"

                if self.session:
                    self.session.add(
                        SemanticMapping(
                            tenant_id=tenant,
                            domain=domain,
                            original_col=col,
                            mapped_col=mapped[col],
                            method=method,
                            status=status,
                        )
                    )

        if self.session:
            self.session.commit()

        # ------------------------------------------------------------
        # STEP 3 — RENAME DATAFRAME
        # ------------------------------------------------------------
        df = df.rename(columns=mapped)

        return df, mapped
