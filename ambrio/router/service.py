# ambrio/router/service.py
import asyncio, zmq, zmq.asyncio, msgpack, logging, re, json
from .session_manager import SessionManager
from .tool_registry import ToolRegistry
from ..ui.ipc.message_protocol import Frame, MsgType
from ambrio.router.memory.token_compressor import compress_text

log = logging.getLogger(__name__)



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
        except Exception as e:
            log.exception(f"Router error for session {frame.session_id}")
            await self._send(identity, Frame(
                session_id=frame.session_id,
                type=MsgType.ERROR,
                payload={"msg": str(e)}
            ))

    async def _stream_chat(self, identity: bytes, frame: Frame) -> None:
        import time
        session      = await self.sessions.get_or_create(frame.session_id)
        user_content = frame.payload.get("content", "")
        messages     = await session.build_context(user_content)
        t_start      = time.monotonic()
        full_answer  = ""
        token_count  = 0

        from ambrio.agents.runner import run_agent
        async for token in run_agent(frame.session_id, user_content, messages):
            token_count += 1
            full_answer += token
            await self._send(identity, Frame(
                session_id=frame.session_id,
                type=MsgType.CHAT_TOKEN,
                payload={"token": token}
            ))

        elapsed = round(time.monotonic() - t_start, 1)
        await session.persist_turn(user_content, full_answer)
        await self.sessions.post_turn_tick(
            frame.session_id, user_content, full_answer)
        await self._send(identity, Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_DONE,
            payload={"model": "multi-agent", "tokens": token_count, "elapsed": elapsed}
        ))

    async def _send(self, identity: bytes, frame: Frame) -> None:
        # ROUTER→DEALER: send [identity, payload] — no empty delimiter
        await self._socket.send_multipart([
            identity,
            msgpack.packb(frame.model_dump())
        ])
