# ambrio/memory/post_turn_worker.py
import asyncio, json, logging, re, uuid
log = logging.getLogger(__name__)

_LESSON_SYSTEM = """Extract durable learnable facts from this conversation turn.
Return ONLY a JSON array of strings. Return [] if nothing worth remembering.
Types to extract:
- User preferences ("user prefers bullet points")
- Persistent facts ("shop name is N.A. MOTORS, Bangalore")
- Tool failures ("doc_save fails on OneDrive paths")
- Learned patterns ("user often asks about brake pads")
Keep each fact under 100 chars. Max 3 facts per turn."""


async def _extract_lessons(user_input: str, assistant_output: str) -> list[str]:
    from ambrio.config import PROVIDER_KEYS
    from ambrio.router.model_router import ModelRouter
    router = ModelRouter(provider_keys=PROVIDER_KEYS)
    messages = [
        {"role": "system", "content": _LESSON_SYSTEM},
        {"role": "user",
         "content": f"User: {user_input[:300]}\nAssistant: {assistant_output[:500]}"},
    ]
    full = ""
    async for chunk in router.stream(messages, task_type="fast"):
        if chunk.get("done"): break
        full += chunk.get("message", {}).get("content", "")
    m = re.search(r'\[.*?\]', full, re.DOTALL)
    if not m: return []
    try:
        lessons = json.loads(m.group())
        return [l for l in lessons if isinstance(l, str) and l.strip()][:3]
    except json.JSONDecodeError:
        return []


class PostTurnWorker:
    def __init__(self, brain, chroma):
        self.brain  = brain
        self.chroma = chroma

    async def process_turn(self, session_id: str,
                            user_input: str, assistant_output: str) -> None:
        try:
            lessons = await _extract_lessons(user_input, assistant_output)
            for lesson in lessons:
                await self.brain.save_lesson(lesson)
                await self.chroma.insert(
                    "__global__", "lesson", lesson, str(uuid.uuid4()))
            if lessons:
                log.info(f"[PostTurn] Committed {len(lessons)} lesson(s)")
        except Exception as e:
            log.error(f"[PostTurn] Worker error (non-fatal): {e}")
