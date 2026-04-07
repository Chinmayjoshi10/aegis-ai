from datetime import datetime, timedelta

class JanitorAgent:
    def __init__(self, pg):
        self.pg = pg

    def decay(self, minutes=10):
        """Decay stale semantic facts.

        Hardening rule: call `execute()` with NO parameters (no lists, no empty dicts).
        This method therefore uses dialect-native time arithmetic without binds.
        """

        try:
            minutes_i = int(minutes)
        except Exception:
            minutes_i = 10
        minutes_i = max(0, min(minutes_i, 24 * 60))

        dialect = "unknown"
        try:
            dialect = str(getattr(getattr(self.pg, "_dialect", None), "__call__", None) and self.pg._dialect())
        except Exception:
            dialect = "unknown"

        # NOTE: `minutes_i` is an internal integer (not user input). Safe to inline.
        if dialect == "sqlite":
            stmt = f"""
            UPDATE semantic_facts
            SET is_active = 0
            WHERE ts < datetime('now','-{minutes_i} minutes') AND is_active = 1
            """.strip()
        else:
            stmt = f"""
            UPDATE semantic_facts
            SET is_active = FALSE
            WHERE ts < (CURRENT_TIMESTAMP - INTERVAL '{minutes_i} minutes') AND is_active = TRUE
            """.strip()

        # Critical: no params passed.
        try:
            self.pg.execute(stmt)
        except Exception:
            # Kernel immunity: janitor must never crash the pipeline.
            return
