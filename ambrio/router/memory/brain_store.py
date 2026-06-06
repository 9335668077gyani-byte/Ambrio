# ambrio/router/memory/brain_store.py
"""
BrainStore — Persistent key-value "brain" for Ambrio.

Stores long-term facts, user profile, and cross-session learnings.
Think of it as Ambrio's long-term memory beyond FTS5 conversation recall.

Schema uses a single `brain` table with namespaced keys:
  - profile.*     → user profile facts (name, job, preferences)
  - fact.*        → domain facts learned across sessions
  - session.*     → per-session summaries keyed by session_id
  - task.*        → open/pending tasks

Designed to be injected into the system prompt at every turn.
"""
import json, time, logging
from .db import Database

log = logging.getLogger(__name__)

BRAIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS brain (
    key         TEXT PRIMARY KEY,
    namespace   TEXT NOT NULL DEFAULT 'fact',
    value       TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 1.0,
    updated_at  INTEGER NOT NULL DEFAULT (unixepoch()),
    source      TEXT DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_brain_ns ON brain(namespace, updated_at DESC);
"""


class BrainStore:
    def __init__(self, db: Database):
        self.db = db

    async def init(self) -> None:
        """Create brain table if not exists."""
        async with self.db.conn() as c:
            for stmt in BRAIN_SCHEMA.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    await c.execute(stmt)
            await c.commit()

    # ── Write ────────────────────────────────────────────────────────────────
    async def set(
        self,
        key: str,
        value: str | dict | list,
        namespace: str = "fact",
        confidence: float = 1.0,
        source: str = "learned"
    ) -> None:
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        async with self.db.conn() as c:
            await c.execute(
                """INSERT INTO brain(key, namespace, value, confidence, updated_at, source)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET
                     value=excluded.value,
                     confidence=excluded.confidence,
                     updated_at=excluded.updated_at,
                     source=excluded.source""",
                (key, namespace, value, confidence, int(time.time()), source)
            )
            await c.commit()

    async def delete(self, key: str) -> None:
        async with self.db.conn() as c:
            await c.execute("DELETE FROM brain WHERE key = ?", (key,))
            await c.commit()

    # ── Read ─────────────────────────────────────────────────────────────────
    async def get(self, key: str) -> str | None:
        async with self.db.conn() as c:
            cur = await c.execute("SELECT value FROM brain WHERE key = ?", (key,))
            row = await cur.fetchone()
        return row[0] if row else None

    async def get_namespace(self, namespace: str, limit: int = 50) -> list[dict]:
        async with self.db.conn() as c:
            cur = await c.execute(
                """SELECT key, value, confidence, updated_at, source
                   FROM brain WHERE namespace = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (namespace, limit)
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ── Ingest summaries ──────────────────────────────────────────────────────
    async def ingest_summary(self, session_id: str, summary: dict) -> None:
        """
        Extract facts and tasks from a session summary dict and store them
        into the brain. This is the self-improvement step — every summarized
        session makes Ambrio smarter for future sessions.
        """
        # Store the full session summary
        await self.set(
            f"session.{session_id}",
            summary,
            namespace="session",
            source="summarizer"
        )

        # Hoist individual facts into brain
        for i, fact in enumerate(summary.get("facts", [])):
            key = f"fact.s{session_id[:8]}.{i}"
            await self.set(key, fact, namespace="fact", confidence=0.9, source="summarizer")

        # Hoist open tasks
        for i, task in enumerate(summary.get("open_tasks", [])):
            key = f"task.s{session_id[:8]}.{i}"
            await self.set(key, task, namespace="task", confidence=1.0, source="summarizer")

        # Hoist entities into profile
        for k, v in summary.get("entities", {}).items():
            await self.set(
                f"profile.{k.lower().replace(' ', '_')}",
                str(v),
                namespace="profile",
                confidence=0.85,
                source="summarizer"
            )

    # ── System prompt block ───────────────────────────────────────────────────
    async def build_memory_block(self) -> str:
        """
        Build a compact memory block for injection into the system prompt.
        Follows Hermes memory-context fencing pattern.
        """
        profile_rows = await self.get_namespace("profile", limit=20)
        fact_rows    = await self.get_namespace("fact",    limit=15)
        task_rows    = await self.get_namespace("task",    limit=10)

        if not (profile_rows or fact_rows or task_rows):
            return ""

        lines = ["<memory-context>",
                 "[System note: The following is Ambrio's recalled long-term memory. "
                 "Use it to personalize responses without re-asking the user.]", ""]

        if profile_rows:
            lines.append("USER PROFILE:")
            for r in profile_rows:
                lines.append(f"  {r['key'].replace('profile.', '')}: {r['value']}")
            lines.append("")

        if fact_rows:
            lines.append("KNOWN FACTS:")
            for r in fact_rows:
                lines.append(f"  - {r['value']}")
            lines.append("")

        if task_rows:
            lines.append("OPEN TASKS:")
            for r in task_rows:
                lines.append(f"  [ ] {r['value']}")
            lines.append("")

        lines.append("</memory-context>")
        return "\n".join(lines)
