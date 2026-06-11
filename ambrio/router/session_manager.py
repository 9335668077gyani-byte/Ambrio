# ambrio/router/session_manager.py
import asyncio, uuid, logging
from .memory.db            import Database
from .memory.fts5_store    import FTS5Store
from .memory.brain_store   import BrainStore
from .memory.learning_loop import LearningLoop
from .context_pruner       import ContextPruner
from .ollama_client        import OllamaClient

log = logging.getLogger(__name__)


class Session:
    def __init__(self, session_id: str, db: Database, brain: BrainStore, ollama: OllamaClient, chroma=None):
        self.id      = session_id
        self.db      = db
        self.brain   = brain
        self.store   = FTS5Store(db)
        self.pruner  = ContextPruner(
            chroma=chroma,
            fts5=self.store,
            session_id=session_id,
            brain=brain
        )
        self.ollama  = ollama
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
        self._history.append({"role": "tool", "content": str(result)})


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._db:       Database | None = None
        self._brain:    BrainStore | None = None
        self._loop:     LearningLoop | None = None
        self._ollama:   OllamaClient = OllamaClient()
        self._model_router = None   # set after init via set_model_router()
        self._chroma       = None
        self._post_turn_worker = None
        self._bg_tasks: set = set()  # strong refs prevent GC of fire-and-forget tasks

    async def init(self, db_path: str = "ambrio.db") -> None:
        self._db = Database(db_path)
        await self._db.init()

        # Init brain store (adds brain table to same DB)
        self._brain = BrainStore(self._db)
        await self._brain.init()

        # Learning loop
        self._loop = LearningLoop(self._db, self._brain, self._ollama)

        async with self._db.conn() as c:
            await c.execute(
                "INSERT OR IGNORE INTO sessions(id,title) VALUES('__global__','Global')"
            )
            await c.commit()

        from ambrio.memory.chroma_store     import ChromaStore
        from ambrio.memory.post_turn_worker import PostTurnWorker
        self._chroma = ChromaStore()   # persist_dir=None → AMBRIO_CHROMA_DIR env var takes effect
        await self._chroma.init()
        self._post_turn_worker = PostTurnWorker(brain=self._brain, chroma=self._chroma)
        log.info("ChromaStore + PostTurnWorker initialized")

        log.info(f"SessionManager initialized — DB: {db_path}")

    async def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            assert self._db and self._brain, "SessionManager.init() not called"
            async with self._db.conn() as c:
                await c.execute(
                    "INSERT OR IGNORE INTO sessions(id,title) VALUES(?,?)",
                    (session_id, f"Session {session_id[:8]}")
                )
                await c.commit()
            self._sessions[session_id] = Session(
                session_id, self._db, self._brain,
                self._model_router if self._model_router else self._ollama,
                chroma=self._chroma   # NEW — pass ChromaStore instance
            )
        return self._sessions[session_id]

    def set_model_router(self, router) -> None:
        """Inject the ModelRouter so new and existing sessions use it."""
        self._model_router = router
        for session in self._sessions.values():
            session.ollama = router
        log.info("ModelRouter injected into SessionManager")

    def list_session_ids(self) -> list[str]:
        """Return all active session IDs."""
        return list(self._sessions.keys())

    async def post_turn_tick(self, session_id: str,
                              user_input: str = "",
                              assistant_output: str = "") -> None:
        """
        Call after every completed turn. Fires the learning loop
        background check (non-blocking) and dispatches PostTurnWorker
        as a fire-and-forget task.
        """
        if self._loop:
            await self._loop.tick(session_id)
        if user_input and hasattr(self, '_post_turn_worker') and self._post_turn_worker:
            task = asyncio.create_task(
                self._post_turn_worker.process_turn(
                    session_id, user_input, assistant_output)
            )
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)

    @property
    def brain(self) -> BrainStore | None:
        return self._brain
