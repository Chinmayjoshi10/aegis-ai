"""Select the canonical memory backend.

Postgres is optional. If configured but unavailable (missing driver / cannot
create engine), the system MUST self-heal into SQLite/in-memory mode.
"""

from aegis_ai.memory.pg_memory import ENGINE as _PG_ENGINE

if _PG_ENGINE is not None:
    from aegis_ai.memory.pg_memory import AegisPostgresMemory as MemoryBackend
else:
    from aegis_ai.memory.semantic_memory_store import SemanticMemoryStore as MemoryBackend

memory_backend = MemoryBackend()
