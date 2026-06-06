# ambrio/router/memory/summarizer.py
"""
Session Summarizer — distills a conversation into compressed facts.
Inspired by Hermes on_pre_compress / on_session_end lifecycle hooks.

Workflow:
  1. Called when a session exceeds SUMMARY_TRIGGER_TURNS turns
  2. Makes a non-streaming Ollama call asking it to extract key facts
  3. Stores the summary as a special 'summary' message in the DB
  4. Marks old messages as archived so they don't bloat FTS recall
"""
import uuid, logging, json
from .db import Database
from ..ollama_client import OllamaClient

log = logging.getLogger(__name__)

SUMMARY_TRIGGER_TURNS = 20   # summarize after this many messages
SUMMARY_ROLE          = "__summary__"

SUMMARIZE_PROMPT = """You are a memory compression assistant.
Review the following conversation and extract a concise factual summary.
Focus on:
- Key facts the user stated about themselves, their work, or their goals
- Decisions made or conclusions reached
- Specific entities mentioned (names, dates, amounts, part numbers)
- Open questions or pending tasks

Return ONLY a JSON object with this structure:
{
  "summary": "2-4 sentence narrative summary",
  "facts": ["fact 1", "fact 2", ...],
  "open_tasks": ["task 1", ...],
  "entities": {"key": "value"}
}

CONVERSATION:
"""


class SessionSummarizer:
    def __init__(self, db: Database, ollama: OllamaClient | None = None):
        self.db     = db
        self.ollama = ollama or OllamaClient()

    async def should_summarize(self, session_id: str) -> bool:
        """True if session has > SUMMARY_TRIGGER_TURNS unsummarized messages."""
        async with self.db.conn() as c:
            cur = await c.execute(
                """SELECT COUNT(*) FROM messages
                   WHERE session_id = ?
                     AND role NOT IN (?, 'tool')
                     AND tool_name IS NULL""",
                (session_id, SUMMARY_ROLE)
            )
            row = await cur.fetchone()
            count = row[0] if row else 0
        return count > SUMMARY_TRIGGER_TURNS

    async def summarize(self, session_id: str) -> dict | None:
        """
        Summarize the session and store result. Returns the parsed summary dict,
        or None on failure. Safe to call multiple times — idempotent on success.
        """
        messages = await self._load_unsummarized(session_id)
        if len(messages) < 4:
            return None  # not enough to summarize

        # Build transcript
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )

        log.info(f"Summarizing session {session_id[:8]} ({len(messages)} messages)")

        summary_dict = await self._call_llm(transcript)
        if not summary_dict:
            return None

        await self._persist(session_id, summary_dict, messages)
        log.info(f"Summary stored for session {session_id[:8]}: {len(summary_dict.get('facts', []))} facts")
        return summary_dict

    async def _call_llm(self, transcript: str) -> dict | None:
        prompt = SUMMARIZE_PROMPT + transcript[:6000]  # hard cap
        full_response = ""
        try:
            async for chunk in self.ollama.stream([
                {"role": "user", "content": prompt}
            ]):
                if chunk.get("done"):
                    break
                full_response += chunk.get("message", {}).get("content", "")

            # Extract JSON from response
            start = full_response.find("{")
            end   = full_response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(full_response[start:end])
        except Exception as e:
            log.warning(f"Summarization LLM call failed: {e}")
        return None

    async def _load_unsummarized(self, session_id: str) -> list[dict]:
        """Load messages that haven't been included in a summary yet."""
        async with self.db.conn() as c:
            cur = await c.execute(
                """SELECT id, role, content FROM messages
                   WHERE session_id = ?
                     AND role NOT IN (?, 'tool')
                     AND tool_args IS NULL
                   ORDER BY ts ASC""",
                (session_id, SUMMARY_ROLE)
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def _persist(
        self, session_id: str, summary: dict, source_messages: list[dict]
    ) -> None:
        """Store summary in dedicated summaries table + mark source messages as archived."""
        summary_text = json.dumps(summary, ensure_ascii=False)

        async with self.db.conn() as c:
            # Ensure summaries table exists
            await c.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    id          TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    ts          INTEGER NOT NULL DEFAULT (unixepoch())
                )
            """)
            await c.execute(
                "INSERT INTO session_summaries(id, session_id, content) VALUES (?,?,?)",
                (str(uuid.uuid4()), session_id, summary_text)
            )
            # Mark source messages as archived
            ids          = [m["id"] for m in source_messages]
            placeholders = ",".join("?" * len(ids))
            await c.execute(
                f"UPDATE messages SET tool_args = 'archived' WHERE id IN ({placeholders})",
                ids
            )
            await c.commit()

    async def load_latest_summary(self, session_id: str) -> dict | None:
        """Load the most recent summary for injection into system prompt."""
        async with self.db.conn() as c:
            # Ensure table exists before querying
            await c.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    content TEXT NOT NULL, ts INTEGER NOT NULL DEFAULT (unixepoch())
                )
            """)
            cur = await c.execute(
                """SELECT content FROM session_summaries
                   WHERE session_id = ? ORDER BY ts DESC LIMIT 1""",
                (session_id,)
            )
            row = await cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None
