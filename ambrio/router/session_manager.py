# ambrio/router/session_manager.py
import uuid
from .memory.db import Database
from .memory.fts5_store import FTS5Store
from .context_pruner import ContextPruner
from .ollama_client import OllamaClient

class Session:
    def __init__(self, session_id: str, db: Database):
        self.id      = session_id
        self.db      = db
        self.store   = FTS5Store(db)
        self.pruner  = ContextPruner(self.store, session_id)
        self.ollama  = OllamaClient()
        self._history: list[dict] = []

    async def build_context(self, user_content: str) -> list[dict]:
        return await self.pruner.build(user_content, self._history)

    async def persist_turn(self, user_content: str, assistant_content: str = "") -> None:
        uid = str(uuid.uuid4())
        aid = str(uuid.uuid4())
        await self.store.insert(self.id, "user", user_content, uid)
        if assistant_content:
            await self.store.insert(self.id, "assistant", assistant_content, aid)
        self._history.append({"role": "user", "content": user_content})
        if assistant_content:
            self._history.append({"role": "assistant", "content": assistant_content})

    def inject_tool_result(self, result: dict) -> None:
        self._history.append({
            "role":    "tool",
            "content": str(result)
        })


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._db: Database | None = None

    async def init(self, db_path: str = "ambrio.db") -> None:
        self._db = Database(db_path)
        await self._db.init()
        async with self._db.conn() as c:
            await c.execute(
                "INSERT OR IGNORE INTO sessions(id,title) VALUES('__global__','Global')"
            )
            await c.commit()

    async def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            assert self._db is not None, "SessionManager.init() must be called first"
            async with self._db.conn() as c:
                await c.execute(
                    "INSERT OR IGNORE INTO sessions(id,title) VALUES(?,?)",
                    (session_id, f"Session {session_id[:8]}")
                )
                await c.commit()
            self._sessions[session_id] = Session(session_id, self._db)
        return self._sessions[session_id]
