# ambrio/router/memory/learning_loop.py
"""
LearningLoop — the self-improvement engine.

Triggered post-turn. Checks whether a session needs summarization,
runs the summarizer, then ingests the summary into BrainStore.

This is the Hermes on_session_end / sync_all equivalent for Ambrio.

Lifecycle:
  ┌──────────┐     every turn     ┌───────────────┐
  │  Router  │ ─── tick() ───▶   │  LearningLoop  │
  └──────────┘                   └───────┬────────┘
                                         │ if turns > 20
                                   ┌─────▼──────────┐
                                   │  Summarizer    │  (LLM call)
                                   └─────┬──────────┘
                                         │ summary dict
                                   ┌─────▼──────────┐
                                   │  BrainStore    │  (persist facts)
                                   └────────────────┘
"""
import asyncio, logging
from .summarizer  import SessionSummarizer
from .brain_store import BrainStore
from .db          import Database
from ..ollama_client import OllamaClient

log = logging.getLogger(__name__)


class LearningLoop:
    def __init__(self, db: Database, brain: BrainStore, ollama: OllamaClient):
        self.summarizer = SessionSummarizer(db, ollama)
        self.brain      = brain
        self._pending: set[str] = set()   # sessions queued for summarization

    async def tick(self, session_id: str) -> None:
        """
        Call this after every turn completes. Non-blocking — actual
        summarization is dispatched as a background asyncio task.
        """
        if session_id in self._pending:
            return  # already queued

        should = await self.summarizer.should_summarize(session_id)
        if should:
            self._pending.add(session_id)
            asyncio.create_task(self._run(session_id))

    async def _run(self, session_id: str) -> None:
        """Background task: summarize → ingest into brain."""
        try:
            log.info(f"LearningLoop: summarizing session {session_id[:8]}")
            summary = await self.summarizer.summarize(session_id)
            if summary:
                await self.brain.ingest_summary(session_id, summary)
                log.info(
                    f"LearningLoop: ingested {len(summary.get('facts', []))} facts "
                    f"+ {len(summary.get('open_tasks', []))} tasks from {session_id[:8]}"
                )
        except Exception as e:
            log.error(f"LearningLoop failed for {session_id[:8]}: {e}")
        finally:
            self._pending.discard(session_id)

    async def force_summarize(self, session_id: str) -> dict | None:
        """Force an immediate synchronous summarization (for testing / manual trigger)."""
        summary = await self.summarizer.summarize(session_id)
        if summary:
            await self.brain.ingest_summary(session_id, summary)
        return summary
