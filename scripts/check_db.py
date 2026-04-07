from aegis_ai.memory.semantic_memory_store import SemanticMemoryStore

store = SemanticMemoryStore()
contract = store.load_contract('demo_factory')
print('stored_contract:', contract)
