# ambrio/memory/chroma_store.py
"""
ChromaDB-backed semantic memory store.

Two modes controlled by CHROMA_MODE environment variable:
  - "embedded" (default) → ChromaDB PersistentClient — runs in-process, single machine.
                           Used for: local dev without Docker, unit tests.
  - "http"               → ChromaDB HttpClient — connects to remote ChromaDB server.
                           Used for: Docker Compose (chromadb service), production.

Config env vars:
  CHROMA_MODE     = "embedded" | "http"   (default: "embedded")
  CHROMA_HOST     = hostname              (default: "localhost")
  CHROMA_PORT     = port number           (default: 8000)
  CHROMA_AUTH_TOKEN = bearer token        (optional, prod only)
  AMBRIO_CHROMA_DIR = /path/to/persist    (embedded mode only, default: ./ambrio_chroma)
"""
import asyncio, logging, os, uuid
log = logging.getLogger(__name__)

_CHROMA_MODE      = os.environ.get("CHROMA_MODE",      "embedded")
_CHROMA_HOST      = os.environ.get("CHROMA_HOST",      "localhost")
_CHROMA_PORT      = int(os.environ.get("CHROMA_PORT",  "8000"))
_CHROMA_TOKEN     = os.environ.get("CHROMA_AUTH_TOKEN", "")
_CHROMA_PERSIST   = os.environ.get("AMBRIO_CHROMA_DIR", "./ambrio_chroma")


class ChromaStore:
    """
    Semantic vector memory store — wraps ChromaDB with all-MiniLM-L6-v2 embeddings.

    Usage:
        store = ChromaStore()      # picks up CHROMA_MODE from env
        await store.init()
        await store.insert("session-1", "user", "brake pad discussed", "msg-001")
        results = await store.search("session-1", "brakes", limit=10)
        # → [{"content": "brake pad discussed", "role": "user", "score": 0.91}]
    """

    def __init__(self, persist_dir: str | None = None):
        # persist_dir=":memory:" → ephemeral EphemeralClient (unit tests only)
        self.persist_dir = persist_dir if persist_dir is not None else _CHROMA_PERSIST
        self._collection = None
        self._embedder   = None
        self._mode       = "memory" if persist_dir == ":memory:" else _CHROMA_MODE
        # Unique collection name per :memory: instance so that EphemeralClient
        # (which is a process-level singleton) doesn't leak state between tests.
        self._collection_name = (
            f"ambrio_messages_{uuid.uuid4().hex}"
            if self._mode == "memory"
            else "ambrio_messages"
        )

    async def init(self) -> None:
        """Initialize ChromaDB client + sentence-transformers model (async-safe)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_init)
        log.info(f"ChromaStore initialized — mode={self._mode}"
                 + (f" host={_CHROMA_HOST}:{_CHROMA_PORT}" if self._mode == "http" else
                    f" dir={self.persist_dir}"))

    def _sync_init(self) -> None:
        import chromadb
        from sentence_transformers import SentenceTransformer

        if self._mode == "memory":
            client = chromadb.EphemeralClient()
        elif self._mode == "http":
            headers = {}
            if _CHROMA_TOKEN:
                headers["Authorization"] = f"Bearer {_CHROMA_TOKEN}"
            client = chromadb.HttpClient(
                host=_CHROMA_HOST,
                port=_CHROMA_PORT,
                headers=headers if headers else None,
            )
        else:
            # embedded — default
            import os as _os
            _os.makedirs(self.persist_dir, exist_ok=True)
            client = chromadb.PersistentClient(path=self.persist_dir)

        self._collection = client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        # Cache dir for sentence-transformers model weights
        cache_dir = os.environ.get("ST_CACHE", None)
        self._embedder = SentenceTransformer(
            "all-MiniLM-L6-v2",
            cache_folder=cache_dir,
        )

    # ── Embed ────────────────────────────────────────────────────────────────

    def _embed(self, text: str) -> list[float]:
        return self._embedder.encode(
            text, normalize_embeddings=True, show_progress_bar=False
        ).tolist()

    # ── Write ────────────────────────────────────────────────────────────────

    async def insert(self, session_id: str, role: str,
                     content: str, message_id: str) -> None:
        """Upsert a single message into the vector store."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._sync_upsert, session_id, role, content, message_id)

    def _sync_upsert(self, session_id: str, role: str,
                      content: str, message_id: str) -> None:
        self._collection.upsert(
            ids=[message_id],
            embeddings=[self._embed(content)],
            documents=[content],
            metadatas=[{"session_id": session_id, "role": role}]
        )

    # ── Read ─────────────────────────────────────────────────────────────────

    async def search(self, session_id: str, query: str,
                     limit: int = 10) -> list[dict]:
        """
        Semantic search within a session.
        Returns list of {"content": str, "role": str, "score": float}
        Score = cosine similarity (0.0–1.0). Higher = more relevant.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._sync_search, session_id, query, limit)

    def _sync_search(self, session_id: str, query: str,
                      limit: int) -> list[dict]:
        results = self._collection.query(
            query_embeddings=[self._embed(query)],
            n_results=min(limit, max(1, self._collection.count())),
            where={"session_id": session_id},
            include=["documents", "metadatas", "distances"]
        )
        docs  = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]
        return [
            {
                "content": doc,
                "role":    meta.get("role", "unknown"),
                "score":   round(max(0.0, 1.0 - dist), 4),
            }
            for doc, meta, dist in zip(docs, metas, dists)
        ]

    async def delete_session(self, session_id: str) -> int:
        """Delete all vectors for a session. Returns count deleted."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_delete, session_id)

    def _sync_delete(self, session_id: str) -> int:
        existing = self._collection.get(where={"session_id": session_id})
        ids = existing.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)
