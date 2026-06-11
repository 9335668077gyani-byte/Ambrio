# ambrio/api/server.py
import asyncio, json as _json, time, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from ambrio.api.models import ChatDone, ErrorMsg, HealthResponse
from ambrio.agents.runner import run_agent  # Fix 6 — top-level import, not in hot loop

log = logging.getLogger(__name__)

VERSION = "4.0.0"           # Fix 5 — single source of truth
_session_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize heavy resources once at startup."""
    global _session_manager
    from ambrio.router.session_manager import SessionManager
    from ambrio.router.model_router    import ModelRouter
    from ambrio.config                 import PROVIDER_KEYS
    _session_manager = SessionManager()
    await _session_manager.init("ambrio.db")
    _session_manager.set_model_router(ModelRouter(provider_keys=PROVIDER_KEYS))
    log.info("Ambrio FastAPI online — ws://localhost:8765/chat/{session_id}")
    yield
    # shutdown — nothing needed


app = FastAPI(title="Ambrio", version=VERSION, lifespan=lifespan)  # Fix 5


@app.get("/health", response_model=HealthResponse)   # Fix 5
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=VERSION)


@app.get("/sessions", response_model=list[str])      # Fix 4
async def list_sessions() -> list[str]:
    if not _session_manager:
        return []
    return _session_manager.list_session_ids()       # Fix 4 — public method


@app.websocket("/chat/{session_id}")
async def chat_ws(ws: WebSocket, session_id: str):
    await ws.accept()

    # Fix 3 — guard against uninitialised session manager
    if _session_manager is None:
        await ws.send_json(
            ErrorMsg(message="Server is initializing, try again shortly.").model_dump()
        )
        await ws.close(code=1013)   # Try Again Later
        return

    log.info("WS connected: %s", session_id)
    try:
        while True:
            # Fix 2 — guard malformed JSON from client
            try:
                data = await ws.receive_json()
            except (_json.JSONDecodeError, ValueError):
                await ws.send_json(
                    ErrorMsg(message="Invalid JSON payload").model_dump()
                )
                continue

            user_content = data.get("content", "").strip()
            if not user_content:
                continue

            session  = await _session_manager.get_or_create(session_id)
            messages = await session.build_context(user_content)
            t_start  = time.monotonic()
            answer   = ""
            tokens   = 0

            async for token in run_agent(session_id, user_content, messages):
                await ws.send_json({"type": "token", "data": token})
                answer += token
                tokens += 1

            elapsed = round(time.monotonic() - t_start, 1)
            await session.persist_turn(user_content, answer)
            await _session_manager.post_turn_tick(session_id, user_content, answer)
            await ws.send_json(
                ChatDone(model="multi-agent", tokens=tokens, elapsed=elapsed).model_dump()
            )

    except WebSocketDisconnect:
        log.info("WS disconnected: %s", session_id)
    except Exception as e:
        log.exception("WS error session=%s", session_id)
        # Fix 1 — close the socket and EXIT; do NOT re-enter the loop
        try:
            await ws.send_json(ErrorMsg(message=str(e)).model_dump())
            await ws.close(code=1011)   # Internal error
        except Exception:
            pass
        return
