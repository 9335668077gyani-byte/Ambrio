# ambrio/router/service.py
import asyncio, zmq, zmq.asyncio, msgpack, logging, re, json
from .session_manager import SessionManager
from .tool_registry import ToolRegistry
from ..ui.ipc.message_protocol import Frame, MsgType
from ambrio.router.memory.token_compressor import compress_text

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
    (re.compile(r'memory_search\s*\(\s*["\'](.+?)["\']\s*(?:,\s*["\'].*?["\']\s*)?\)',
                re.IGNORECASE | re.DOTALL),
     "memory_search", "query"),

    # file_read("path")
    (re.compile(r'file_read\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'file_read', 'path'),

    # file_write("path", ...) — capture path only
    (re.compile(r'file_write\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'file_write', 'path'),

    # file_list("directory")
    (re.compile(r'file_list\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'file_list', 'directory'),

    # file_search("pattern")
    (re.compile(r'file_search\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'file_search', 'pattern'),

    # doc_read("path")
    (re.compile(r'doc_read\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'doc_read', 'path'),

    # doc_extract_table("path")
    (re.compile(r'doc_extract_table\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'doc_extract_table', 'path'),

    # doc_save("path", "content") — two-arg pattern, capture path only (content too large for regex)
    (re.compile(r'doc_save\s*\(\s*["\'](.+?)["\']\s*,', re.IGNORECASE | re.DOTALL),
     'doc_save', 'path'),

    # doc_convert("path", "to_format") — capture path, format extracted separately below
    (re.compile(r'doc_convert\s*\(\s*["\'](.+?)["\']\s*,\s*["\']([\w]+)["\']\s*\)', re.IGNORECASE),
     'doc_convert', 'path'),

    # web_search("query")
    (re.compile(r'web_search\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'web_search', 'query'),

    # web_read("url")
    (re.compile(r'web_read\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'web_read', 'url'),

    # reddit_search("query")
    (re.compile(r'reddit_search\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'reddit_search', 'query'),

    # github_search("query")
    (re.compile(r'github_search\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'github_search', 'query'),

    # file_open("path")
    (re.compile(r'file_open\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'file_open', 'path'),

    # file_show("path")
    (re.compile(r'file_show\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'file_show', 'path'),

    # doc_combine("path1", "path2") or doc_combine("path1", "path2", "name.pdf")
    # captured path1 only — path2 extracted separately in _extract_text_tool_call
    (re.compile(r'doc_combine\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'doc_combine', 'path1'),

    # img_ocr("path")
    (re.compile(r'img_ocr\s*\(\s*["\'](.+?)["\']\s*\)', re.IGNORECASE | re.DOTALL),
     'img_ocr', 'path'),

    # img_passport("path") or img_passport("path", "india")
    (re.compile(r'img_passport\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'img_passport', 'path'),

    # img_resize("path", width, height)
    (re.compile(r'img_resize\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'img_resize', 'path'),

    # img_background("path", "white")
    (re.compile(r'img_background\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'img_background', 'path'),

    # img_rotate("path", 90)
    (re.compile(r'img_rotate\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'img_rotate', 'path'),

    # img_enhance("path", ...)
    (re.compile(r'img_enhance\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'img_enhance', 'path'),

    # img_remove_bg("path")
    (re.compile(r'img_remove_bg\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'img_remove_bg', 'path'),

    # img_upscale("path") or img_upscale("path", 4)
    (re.compile(r'img_upscale\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'img_upscale', 'path'),

    # img_scan_doc("path")
    (re.compile(r'img_scan_doc\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'img_scan_doc', 'path'),

    # img_color_grade("path", "vivid")
    (re.compile(r'img_color_grade\s*\(\s*["\'](.+?)["\']', re.IGNORECASE | re.DOTALL),
     'img_color_grade', 'path'),

]


def _extract_text_tool_call(text: str) -> tuple[str, dict] | None:
    """Return (tool_name, kwargs) if a text-format tool call is found."""
    # Special case: doc_convert needs two args (path + format)
    m = re.search(
        r'doc_convert\s*\(\s*["\'](.+?)["\']\s*,\s*["\']([\w]+)["\']\s*\)',
        text, re.IGNORECASE
    )
    if m:
        return 'doc_convert', {'path': m.group(1).strip(), 'to': m.group(2).strip()}

    # Special case: doc_combine needs path1 + path2 (+ optional out_name)
    m = re.search(
        r'doc_combine\s*\(\s*["\'](.+?)["\']\s*,\s*["\'](.+?)["\']\s*(?:,\s*["\'](.+?)["\'])?\s*\)',
        text, re.IGNORECASE
    )
    if m:
        kwargs = {'path1': m.group(1).strip(), 'path2': m.group(2).strip()}
        if m.group(3):
            kwargs['out_name'] = m.group(3).strip()
        return 'doc_combine', kwargs

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
        import ambrio.router.tools.file_tool           # noqa
        import ambrio.router.tools.doc_tool            # noqa
        import ambrio.router.tools.convert_tool        # noqa
        import ambrio.router.tools.web_tool            # noqa
        import ambrio.router.tools.img_tool            # noqa

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
        import time
        session   = await self.sessions.get_or_create(frame.session_id)
        messages  = await session.build_context(frame.payload.get("content", ""))
        assistant = ""
        token_count = 0
        t_start = time.monotonic()

        # Capture which model alias is chosen for this request
        user_text = frame.payload.get("content", "")
        model_alias = self._model_router._select_model_alias(user_text)
        from ambrio.router.model_registry import get_model
        model_def   = get_model(model_alias)
        provider    = model_def.provider if model_def else "ollama"
        model_id    = model_def.model_id  if model_def else model_alias

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
                                                   assistant, tool_name, tool_args,
                                                   model_alias=model_alias)
                return

            token = msg.get("content", "")
            assistant  += token
            token_count += len(token.split()) if token else 0
            if token:
                await self._send(identity, Frame(
                    session_id=frame.session_id,
                    type=MsgType.CHAT_TOKEN,
                    payload={"token": token}
                ))

        # ── Text-based tool call fallback (small models like llama3.2:1b) ──
        tool_hit = _extract_text_tool_call(assistant)
        if tool_hit:
            tool_name, tool_args = tool_hit
            log.info(f"Text tool call detected: {tool_name}({tool_args})")
            await self._execute_tool_and_reply(identity, frame, session,
                                               assistant, tool_name, tool_args,
                                               model_alias=model_alias)
            return

        # ── Normal text response ────────────────────────────────────
        elapsed = round(time.monotonic() - t_start, 1)
        await session.persist_turn(frame.payload.get("content", ""), assistant)
        await self.sessions.post_turn_tick(frame.session_id)
        await self._send(identity, Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_DONE,
            payload={
                "model":    model_alias,
                "provider": provider,
                "model_id": model_id,
                "tokens":   token_count,
                "elapsed":  elapsed,
            }
        ))

    async def _execute_tool_and_reply(
        self,
        identity:  bytes,
        frame:     Frame,
        session,
        assistant: str,
        tool_name: str,
        tool_args: dict,
        model_alias: str = "ollama/llama3.2-1b",
    ) -> None:
        import time
        """Execute a tool call and stream the result back as a natural answer."""
        t_start = time.monotonic()
        from ambrio.router.model_registry import get_model
        model_def = get_model(model_alias)
        provider  = model_def.provider if model_def else "ollama"
        model_id  = model_def.model_id  if model_def else model_alias

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

        # Compress tool result to save tokens
        final_answer = compress_text(final_answer, max_tokens=400)

        # Stream the answer token by token (word-by-word for smooth UX)
        words   = final_answer.split()
        streamed = ""
        for i, word in enumerate(words):
            token = word + (" " if i < len(words) - 1 else "")
            streamed += token
            await self._send(identity, Frame(
                session_id=frame.session_id,
                type=MsgType.CHAT_TOKEN,
                payload={"token": token}
            ))
            await asyncio.sleep(0.015)

        elapsed = round(time.monotonic() - t_start, 1)
        await session.persist_turn(frame.payload.get("content", ""), streamed)
        await self.sessions.post_turn_tick(frame.session_id)
        await self._send(identity, Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_DONE,
            payload={
                "model":    model_alias,
                "provider": provider,
                "model_id": model_id,
                "tokens":   len(streamed.split()),
                "elapsed":  elapsed,
                "tool":     tool_name,
            }
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
