# ambrio/api/server.py
import asyncio, time, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from ambrio.api.models import ChatDone, ErrorMsg

log = logging.getLogger(__name__)

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


app = FastAPI(title="Ambrio", version="4.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "4.0.0"}


@app.get("/sessions")
async def list_sessions():
    if not _session_manager:
        return []
    return list(_session_manager._sessions.keys())


@app.websocket("/chat/{session_id}")
async def chat_ws(ws: WebSocket, session_id: str):
    await ws.accept()
    log.info("WS connected: %s", session_id)
    try:
        while True:
            data         = await ws.receive_json()
            user_content = data.get("content", "").strip()
            if not user_content:
                continue

            session  = await _session_manager.get_or_create(session_id)
            messages = await session.build_context(user_content)
            t_start  = time.monotonic()
            answer   = ""
            tokens   = 0

            from ambrio.agents.runner import run_agent
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
        try:
            await ws.send_json(ErrorMsg(message=str(e)).model_dump())
        except Exception:
            pass
