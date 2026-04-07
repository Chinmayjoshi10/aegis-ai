from collections import defaultdict
from aegis_ai.memory.semantic_memory_store import SemanticMemoryStore

class SemanticGroupingEngine:
    def __init__(self, tenant):
        self.tenant = tenant
        self.semantic = SemanticMemoryStore()

    def build_groups(self, df):
        # load the persisted contract (dict mapping column -> metadata)
        contracts = self.semantic.load_contract(self.tenant) or {}
        groups = defaultdict(list)
        for c in df.columns:
            groups[contracts.get(c, {}).get("meaning_label", "ungrouped")].append(c)
        return groups
