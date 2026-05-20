import json
import logging
log = logging.getLogger("aegis_ai.sanitizer.semantic_mapper")
from sqlalchemy.orm import Session

# LLM provider — optional, disabled when no API key is configured
try:
    from aegis_ai.llm.call_gemma import _get_provider as _get_llm_provider
    _LLMProvider = True  # Sentinel — actual provider fetched lazily
except ImportError:
    _LLMProvider = None
    _get_llm_provider = None


class _NoOpLLM:
    """Used when no LLM is configured. Falls back to original column names."""
    def is_available(self): return False
    def generate(self, *a, **kw): raise RuntimeError("No LLM configured")
from aegis_ai.db.baselines.semantic_mapping import SemanticMapping


# -------------------------------------------------------------------
# CANONICAL FIELD DEFINITIONS
# -------------------------------------------------------------------
# These are schema-level meanings.
# They DO NOT contain numeric logic.
# They are strictly column-name normalization targets.
# -------------------------------------------------------------------

CANONICAL_FIELDS = {

    # ═══════════════════════════════════════════════
    # IDENTIFIERS
    # ═══════════════════════════════════════════════
    "Transaction_ID": ["transaction id", "txn id", "txn_id", "order id", "order_no",
                       "invoice id", "invoice_no", "receipt id", "booking id"],
    "Customer_ID":    ["customer id", "cust id", "client id", "buyer id", "account id",
                       "member id", "subscriber id", "user id"],
    "Product_ID":     ["product id", "prod id", "item id", "sku", "article id", "part id",
                       "material id", "item_no", "part_no"],
    "Employee_ID":    ["employee id", "emp id", "staff id", "worker id", "personnel id"],
    "Supplier_ID":    ["supplier id", "vendor id", "partner id", "provider id"],

    # ═══════════════════════════════════════════════
    # TIMESTAMPS
    # ═══════════════════════════════════════════════
    "Order_Date":      ["order date", "order_date", "purchase date", "sale date",
                        "booking date", "transaction date", "invoice date"],
    "Event_Timestamp": ["event time", "timestamp", "event timestamp", "datetime",
                        "date_time", "recorded_at", "logged_at", "occurred_at"],
    "Created_At":      ["created at", "created_at", "creation date", "open date",
                        "start date", "join date", "enrollment date"],
    "Posting_Date":    ["posting date", "ship date", "delivery date", "dispatch date",
                        "fulfillment date", "completion date", "close date"],

    # ═══════════════════════════════════════════════
    # SALES DOMAIN
    # ═══════════════════════════════════════════════
    "Revenue":         ["revenue", "sales", "turnover", "gross sales", "net sales",
                        "sales income", "receipts", "proceeds", "sales_amount", "sale_value"],
    "Quantity":        ["qty", "quantity", "units sold", "items sold",
                        "pieces", "no of units", "num_units"],
    "Price_per_Unit":  ["unit price", "price per unit", "ppu", "selling price",
                        "list price", "mrp", "cost price"],
    "Total_Amount":    ["total", "total amount", "total_sale", "net amount",
                        "invoice amount", "bill amount", "order value", "order_total"],
    "Discount":        ["discount", "discount amount", "rebate", "markdown", "allowance"],
    "Discount_Rate":   ["discount rate", "discount_rate", "discount pct",
                        "discount percent", "discount percentage", "promo rate"],
    "Profit":          ["profit", "net profit", "gross profit", "earnings",
                        "surplus", "gain", "margin_amount"],
    "Profit_Margin":   ["margin", "profit margin", "gross margin", "net margin",
                        "margin_pct", "margin_rate", "profitability"],
    "Returns":         ["returns", "return amount", "refund", "refund amount",
                        "chargeback", "return_qty", "returned units"],

    # ═══════════════════════════════════════════════
    # FINANCE / ACCOUNTING DOMAIN
    # ═══════════════════════════════════════════════
    "Cost":             ["cost", "expense", "expenditure", "outflow",
                         "operating cost", "total cost", "cost_amount"],
    "Ad_Spend":          ["ad spend", "ad_spend", "advertising spend", "marketing spend",
                         "marketing budget", "ad budget", "campaign spend",
                         "media spend", "promo spend"],
    "Cost_per_Unit":    ["cost per unit", "unit cost", "cogs per unit", "variable cost"],
    "COGS":             ["cogs", "cost of goods", "cost of goods sold", "cost of sales"],
    "Operating_Expense":["opex", "operating expense", "overhead", "admin expense"],
    "Tax":              ["tax", "gst", "vat", "tax amount", "duty", "levy"],
    "Cash_Flow":        ["cash flow", "cashflow", "net cash", "free cash flow", "fcf"],
    "Account_Balance":  ["balance", "account balance", "closing balance",
                         "outstanding", "payable", "receivable", "balance_amount"],
    "Payment_Amount":   ["payment", "payment amount", "paid amount", "settled",
                         "remittance", "collection"],

    # ═══════════════════════════════════════════════
    # HR DOMAIN
    # ═══════════════════════════════════════════════
    "Employee_Age":      ["employee age", "worker age", "staff age"],
    "Salary":            ["salary", "wage", "compensation", "monthly income",
                          "annual income", "ctc", "monthly salary", "annual salary",
                          "remuneration", "take home", "net pay", "basic pay"],
    "Tenure":            ["tenure", "experience", "years of service", "seniority",
                          "service years", "months_employed"],
    "Attrition":         ["attrition", "turnover", "churn", "resignation",
                          "voluntary exit", "attrition_rate"],
    "Headcount":         ["headcount", "employee count", "staff count", "workforce",
                          "fte", "full time equivalent"],
    "Absenteeism":       ["absenteeism", "absence", "leave days", "sick days",
                          "days absent", "absent_rate"],
    "Performance_Score": ["performance", "performance score", "rating", "appraisal",
                          "kpi score", "evaluation score", "review score"],
    "Satisfaction_Score":["satisfaction", "employee satisfaction", "engagement",
                          "happiness score", "esat"],

    # ═══════════════════════════════════════════════
    # OPERATIONS / MANUFACTURING DOMAIN
    # ═══════════════════════════════════════════════
    "Production_Volume": ["production", "output", "units produced", "manufactured",
                          "production_qty", "throughput", "yield"],
    "Defect_Rate":       ["defect rate", "reject rate", "scrap rate", "failure rate",
                          "error rate", "fault rate", "defective_pct"],
    "Defect_Count":      ["defects", "defect count", "rejects", "scrap", "failures",
                          "faults", "non_conformance"],
    "Downtime":          ["downtime", "idle time", "machine downtime", "stoppage",
                          "breakdown time", "unplanned downtime"],
    "Uptime":            ["uptime", "availability", "machine availability",
                          "operational time", "running time"],
    "OEE":               ["oee", "overall equipment effectiveness", "equipment efficiency"],
    "Cycle_Time":        ["cycle time", "processing time", "takt time",
                          "throughput time", "production time"],
    "Energy_Usage":      ["energy", "power usage", "kwh", "usage_kwh", "electricity",
                          "power consumption", "energy consumption", "watt"],
    "Power_Factor":      ["power factor", "lagging_power_factor",
                          "leading_power_factor", "power_factor"],
    "Reactive_Power":    ["reactive power", "kvarh", "reactive_power",
                          "lagging_current_reactive", "leading_current_reactive"],
    "CO2_Emissions":     ["co2", "carbon", "emissions", "co2_tco2", "carbon dioxide",
                          "greenhouse", "ghg", "carbon emissions"],
    "Temperature":       ["temperature", "temp", "celsius", "fahrenheit",
                          "process temp", "air temp", "ambient temp"],
    "Pressure":          ["pressure", "psi", "bar", "pascal", "kpa"],
    "Quality_Score":     ["quality", "quality score", "grade", "quality_index",
                          "quality rating", "inspection score"],
    "Maintenance_Cost":  ["maintenance", "maintenance cost", "repair cost", "service cost"],
    "Inventory_Level":   ["inventory", "stock", "stock level", "on hand",
                          "warehouse qty", "inventory_qty"],

    # ═══════════════════════════════════════════════
    # LOGISTICS DOMAIN
    # ═══════════════════════════════════════════════
    "Delivery_Time":  ["delivery time", "transit time", "shipping time",
                       "fulfillment time", "turnaround", "tat", "days_to_deliver"],
    "Delivery_Cost":  ["delivery cost", "shipping cost", "freight", "logistics cost",
                       "transport cost", "carrier cost", "freight_charge"],
    "On_Time_Rate":   ["on time", "on_time_rate", "otd", "on time delivery",
                       "delivery performance", "service level"],
    "Distance":       ["distance", "km", "miles", "route distance", "trip distance"],
    "Weight":         ["weight", "gross weight", "net weight", "shipment weight",
                       "cargo weight", "tonnage"],
    "Fill_Rate":      ["fill rate", "order fill", "fulfillment rate", "availability rate"],

    # ═══════════════════════════════════════════════
    # CUSTOMER / GENERAL
    # ═══════════════════════════════════════════════
    "Customer_Age":      ["customer age", "cust age", "buyer age", "client age"],
    "Age":               ["age", "years of age", "person age"],
    "Gender":            ["gender", "sex"],
    "CLV":               ["clv", "ltv", "lifetime value", "customer lifetime value"],
    "NPS":               ["nps", "net promoter", "promoter score", "customer score"],
    "Churn_Rate":        ["churn", "churn rate", "customer churn", "cancellation rate"],
    "Conversion_Rate":   ["conversion", "conversion rate", "cvr", "close rate"],
    "Product_Category":  ["category", "product category", "prod cat", "item category",
                          "product_type", "segment"],
    "Region":            ["region", "zone", "territory", "area", "geography", "market"],
    "Channel":           ["channel", "sales channel", "distribution channel", "platform"],
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

# Import universal column filter
from aegis_ai.sanitizer.column_filter import is_valid_column_name


def _is_valid_column(col: str) -> bool:
    """
    Wrapper around universal column intelligence filter.
    Returns True if column should be analyzed as a business metric.
    """
    return is_valid_column_name(col)


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
        if _LLMProvider and _get_llm_provider:
            try:
                self.llm = _get_llm_provider()
            except Exception:
                self.llm = _NoOpLLM()
        else:
            self.llm = _NoOpLLM()
        self.ollama_timeout_s = int(ollama_timeout_s or 8)

    # ----------------------------------------------------------------
    # RULE-BASED MAPPING (PRIMARY)
    # ----------------------------------------------------------------
    def _rule_map(self, col: str) -> str | None:
        col_norm = col.strip().lower()
        # Normalize separators so "usage_kwh" becomes "usage kwh"
        import re
        col_words = re.sub(r"[_\-\.\s]+", " ", col_norm).strip()

        for canon, variants in CANONICAL_FIELDS.items():
            # Exact match (normalized)
            if col_norm == canon.lower():
                return canon
            for v in variants:
                # Whole-word match only — prevents "age" matching "usage"
                pattern = r"\b" + re.escape(v) + r"\b"
                if re.search(pattern, col_words):
                    return canon
        return None

    # ----------------------------------------------------------------
    # LLM FALLBACK — COLUMN NAMES ONLY
    # ----------------------------------------------------------------
    def _llm_suggest(self, columns: list[str]) -> dict:
        """
        Claude API fallback for column name mapping.
        Only called for columns the rule-based mapper could not resolve.
        LLM MUST ONLY see column names — never data values.
        """

        if not self.llm.is_available():
            # No API key configured — skip LLM, use original names
            return {col: col for col in columns}

        canonical_list = list(CANONICAL_FIELDS.keys())
        prompt = f"""You are a semantic schema mapper for an enterprise analytics system.

Map each column name to the best match from the canonical list, or return the original name if no match fits.

Canonical fields: {canonical_list}

Rules:
- Only use column NAMES — never guess about data values
- Only map if you are confident — uncertain = return original name
- Return valid JSON only, no explanation, no markdown
- Format: {{"original_col_name": "canonical_name_or_original"}}

Columns to map: {columns}"""

        try:
            raw = self.llm.generate(prompt, timeout=self.ollama_timeout_s)
            # Strip any markdown code fences if present
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            mapping = json.loads(raw)
            if isinstance(mapping, dict):
                return mapping
        except Exception as e:
            log.debug(f"LLM mapping skipped: {e}")

        return {col: col for col in columns}

    # ----------------------------------------------------------------
    # MAIN ENTRY
    # ----------------------------------------------------------------
    def map_columns(self, df, tenant: str, domain: str, *, preserve_columns: list[str] | None = None):
        """
        Returns:
        - cleaned + renamed DataFrame
        - semantic mapping dict {original_col -> mapped_col}

        Args:
            preserve_columns: columns to keep in the DataFrame even if the
                              metric filter would drop them (e.g. profiler-
                              identified dimensions needed by segment engine).
        """

        # ------------------------------------------------------------
        # STEP 0 — HARD DROP JUNK COLUMNS
        # Dimension columns identified by the profiler are preserved
        # so that the segment engine can use them downstream.
        # ------------------------------------------------------------
        preserve = set(preserve_columns or [])
        valid_cols = [c for c in df.columns if _is_valid_column(c) or c in preserve]
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