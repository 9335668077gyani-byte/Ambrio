# ambrio/router/service.py
import asyncio, zmq, zmq.asyncio, msgpack, logging
from .session_manager import SessionManager
from .tool_registry import ToolRegistry
from ..ui.ipc.message_protocol import Frame, MsgType

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
            # ROUTER socket: [identity, empty_delimiter, payload]
            # Guard against malformed frames
            if len(parts) < 3:
                log.warning(f"Malformed ZMQ frame ({len(parts)} parts), skipping")
                continue
            identity = parts[0]
            raw      = parts[-1]   # payload is always last
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
            # Tool call detected — gate through UI for human approval
            if msg.get("tool_calls"):
                tool_call = msg["tool_calls"][0]
                self._suspended[frame.session_id] = (identity, frame)
                await self._send(identity, Frame(
                    session_id=frame.session_id,
                    type=MsgType.TOOL_CALL,
                    payload=tool_call
                ))
                return  # suspend — resume in _resume_after_tool

            token     = msg.get("content", "")
            assistant += token
            if token:
                await self._send(identity, Frame(
                    session_id=frame.session_id,
                    type=MsgType.CHAT_TOKEN,
                    payload={"token": token}
                ))

        await session.persist_turn(frame.payload.get("content", ""), assistant)
        # Fire learning loop check (non-blocking background task)
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

        # Re-enter streaming with injected tool result (empty user content)
        resume_frame = Frame(
            session_id=frame.session_id,
            type=MsgType.CHAT_REQUEST,
            payload={"content": ""}
        )
        await self._stream_chat(identity, resume_frame)

    async def _send(self, identity: bytes, frame: Frame) -> None:
        await self._socket.send_multipart([
            identity, b"",
            msgpack.packb(frame.model_dump())
        ])
