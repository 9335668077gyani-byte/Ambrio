# ambrio/router/service.py
import asyncio, zmq, zmq.asyncio, msgpack, logging, re, json
from .session_manager import SessionManager
from .tool_registry import ToolRegistry
from ..ui.ipc.message_protocol import Frame, MsgType

log = logging.getLogger(__name__)

# ── Text-based tool call extractor ───────────────────────────────────────────
# Small models (llama3.2:1b) can't emit structured JSON tool calls.
# They write tool calls as plain text instead, e.g.:
#   sparepartspro_query("what parts are low?")
#   sparepartspro_sql("SELECT * FROM parts")
#   memory_search("invoice", "session-id")
#
# We detect these patterns and execute them directly in the router,
# then return the result as a natural-language continuation.

_TOOL_PATTERNS = [
    # sparepartspro_query("question")
    (re.compile(r'sparepartspro_query\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     "sparepartspro_query", "question"),

    # sparepartspro_sql("SELECT ...")
    (re.compile(r'sparepartspro_sql\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     "sparepartspro_sql", "sql"),

    # memory_search("query", "session_id")  — session_id optional
    (re.compile(r'memory_search\s*\(\s*["\'](.+?)["\']\s*(?:,\s*["\'].*?["\'])?\s*\)',
                re.IGNORECASE | re.DOTALL),
     "memory_search", "query"),
]


def _extract_text_tool_call(text: str) -> tuple[str, dict] | None:
    """Return (tool_name, kwargs) if a text-format tool call is found."""
    for pattern, tool_name, arg_name in _TOOL_PATTERNS:
        m = pattern.search(text)
        if m:
            return tool_name, {arg_name: m.group(1).strip()}
    return None


class RouterService:
    BIND_ADDR = "tcp://127.0.0.1:5555"

    def __init__(self):
        self.sessions  = SessionManager()
        self.tools     = ToolRegistry()
        self._socket: zmq.asyncio.Socket | None = None
        # Track suspended sessions awaiting TOOL_RESULT
        self._suspended: dict[str, tuple[bytes, Frame]] = {}

    async def start(self, db_path: str = "ambrio.db") -> None:
        await self.sessions.init(db_path)

        # Build multi-model router from .env API keys
        from ambrio.config import PROVIDER_KEYS
        from ambrio.router.model_router import ModelRouter
        self._model_router = ModelRouter(provider_keys=PROVIDER_KEYS)
        self.sessions.set_model_router(self._model_router)

        # Import tools so @tool decorators register
        import ambrio.router.tools.memory_tool        # noqa
        import ambrio.router.tools.sparepartspro_tool  # noqa
        import ambrio.router.tools.sandbox_tool        # noqa

        ctx = zmq.asyncio.Context()
        self._socket = ctx.socket(zmq.ROUTER)
        self._socket.bind(self.BIND_ADDR)
        log.info(f"Cognitive Router bound to {self.BIND_ADDR}")
        await self._recv_loop()

    async def _recv_loop(self) -> None:
        while True:
            parts = await self._socket.recv_multipart()
            # DEALER→ROUTER frame layout: [identity, payload] — 2 parts.
            # (The empty delimiter only exists in REQ/REP, not DEALER/ROUTER)
            if len(parts) < 2:
                log.warning(f"Malformed ZMQ frame ({len(parts)} parts), skipping")
                continue
            identity = parts[0]
            raw      = parts[-1]   # payload is always last part
            try:
                frame = Frame.model_validate(msgpack.unpackb(raw, raw=False))
            except Exception as e:
                log.warning(f"Frame decode error: {e}")
                continue
            asyncio.create_task(self._handle(identity, frame))

    async def _handle(self, identity: bytes, frame: Frame) -> None:
        try:
            match frame.type:
                case MsgType.CHAT_REQUEST:
                    await self._stream_chat(identity, frame)
                case MsgType.TOOL_RESULT:
                    await self._resume_after_tool(identity, frame)
        except Exception as e:
            log.exception(f"Router error for session {frame.session_id}")
            await self._send(identity, Frame(
                session_id=frame.session_id,
                type=MsgType.ERROR,
                payload={"msg": str(e)}
            ))

    async def _stream_chat(self, identity: bytes, frame: Frame) -> None:
        session   = await self.sessions.get_or_create(frame.session_id)
        messages  = await session.build_context(frame.payload.get("content", ""))
        assistant = ""

        async for chunk in session.ollama.stream(messages, tools=self.tools.schema()):
            if chunk.get("done"):
                break
            msg = chunk.get("message", {})

            # ── Structured tool call (models that support it) ─────────────────
            if msg.get("tool_calls"):
                tool_call = msg["tool_calls"][0]
                tool_name = tool_call.get("function", {}).get("name", "")
                tool_args = tool_call.get("function", {}).get("arguments", {})
                log.info(f"Structured tool call: {tool_name}({tool_args})")
                await self._execute_tool_and_reply(identity, frame, session,
                                                   assistant, tool_name, tool_args)
                return

            token     = msg.get("content", "")
            assistant += token
            if token:
                await self._send(identity, Frame(
                    session_id=frame.session_id,
                    type=MsgType.CHAT_TOKEN,
                    payload={"token": token}
                ))

        # ── Text-based tool call fallback (small models like llama3.2:1b) ─────
        tool_hit = _extract_text_tool_call(assistant)
        if tool_hit:
            tool_name, tool_args = tool_hit
            log.info(f"Text tool call detected: {tool_name}({tool_args})")
            await self._execute_tool_and_reply(identity, frame, session,
                                               assistant, tool_name, tool_args)
            return

        # ── Normal text response ──────────────────────────────────────────────
        await session.persist_turn(frame.payload.get("content", ""), assistant)
        await self.sessions.post_turn_tick(frame.session_id)
        await self._send(identity, Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_DONE,
            payload={}
        ))

    async def _execute_tool_and_reply(
        self,
        identity:  bytes,
        frame:     Frame,
        session,
        assistant: str,
        tool_name: str,
        tool_args: dict
    ) -> None:
        """Execute a tool call and stream the result back as a natural answer."""
        # Execute the tool
        try:
            result = await self.tools.dispatch(tool_name, tool_args)
        except Exception as e:
            result = {"error": str(e)}

        log.info(f"Tool result: {str(result)[:200]}")

        # For ERP queries, the answer is already in result["answer"]
        if isinstance(result, dict) and "answer" in result and not result.get("error"):
            final_answer = result["answer"]
        elif isinstance(result, dict) and result.get("error"):
            final_answer = f"I ran into an issue: {result['error']}"
        else:
            final_answer = json.dumps(result, default=str)[:500]

        # Stream the answer token by token (word-by-word for smooth UX)
        words = final_answer.split()
        streamed = ""
        for i, word in enumerate(words):
            token = word + (" " if i < len(words) - 1 else "")
            streamed += token
            await self._send(identity, Frame(
                session_id=frame.session_id,
                type=MsgType.CHAT_TOKEN,
                payload={"token": token}
            ))
            await asyncio.sleep(0.015)   # ~65 words/sec — feels like streaming

        await session.persist_turn(frame.payload.get("content", ""), streamed)
        await self.sessions.post_turn_tick(frame.session_id)
        await self._send(identity, Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_DONE,
            payload={}
        ))

    async def _resume_after_tool(self, identity: bytes, frame: Frame) -> None:
        result = await self.tools.dispatch(
            frame.payload["tool_name"],
            frame.payload.get("tool_args", {})
        )
        session = await self.sessions.get_or_create(frame.session_id)
        session.inject_tool_result(result)

        resume_frame = Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_REQUEST,
            payload={"content": ""}
        )
        await self._stream_chat(identity, resume_frame)

    async def _send(self, identity: bytes, frame: Frame) -> None:
        # ROUTER→DEALER: send [identity, payload] — no empty delimiter
        await self._socket.send_multipart([
            identity,
            msgpack.packb(frame.model_dump())
        ])
