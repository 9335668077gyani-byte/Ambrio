# tests/unit/test_post_turn_worker.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from ambrio.memory.post_turn_worker import PostTurnWorker


async def test_worker_extracts_and_commits_lessons():
    brain  = MagicMock(); brain.save_lesson  = AsyncMock()
    chroma = MagicMock(); chroma.insert      = AsyncMock()
    worker = PostTurnWorker(brain=brain, chroma=chroma)
    with patch("ambrio.memory.post_turn_worker._extract_lessons",
               new_callable=AsyncMock) as ex:
        ex.return_value = ["user prefers bullet points", "shop name is N.A. MOTORS"]
        await worker.process_turn("s1", "give a list", "• item1\n• item2")
    assert brain.save_lesson.call_count == 2
    assert chroma.insert.call_count == 2


async def test_worker_silent_on_empty_lessons():
    brain  = MagicMock(); brain.save_lesson  = AsyncMock()
    chroma = MagicMock(); chroma.insert      = AsyncMock()
    worker = PostTurnWorker(brain=brain, chroma=chroma)
    with patch("ambrio.memory.post_turn_worker._extract_lessons",
               new_callable=AsyncMock) as ex:
        ex.return_value = []
        await worker.process_turn("s1", "hi", "hello!")
    brain.save_lesson.assert_not_called()
