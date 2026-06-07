# ambrio/router/context_pruner.py
import tiktoken
from .memory.fts5_store  import FTS5Store
from .memory.brain_store import BrainStore
from .memory.token_compressor import compress_messages, compress_text

CONTEXT_BUDGET   = 7000   # tokens — leaves ~1192 for response
RECENT_MSGS_KEEP = 6      # always keep last N verbatim
enc = tiktoken.get_encoding("cl100k_base")

BASE_SYSTEM_PROMPT = (
    "You are Ambrio, a local AI assistant for a spare parts shop ERP called SparePartsPro.\n\n"
    "TOOLS — call them EXACTLY like this when needed:\n"
    "  sparepartspro_query(\"your question in plain English\")\n"
    "  sparepartspro_sql(\"SELECT ... FROM parts WHERE ...\")\n"
    "  memory_search(\"query\")\n\n"
    "RULES:\n"
    "1. If the user asks about stock, parts, inventory, sales, invoices, revenue, customers, or vendors "
    "→ IMMEDIATELY call sparepartspro_query(\"their question\"). Do NOT explain first.\n"
    "2. Call the tool on its own line, nothing else.\n"
    "3. Never say 'I will query' or 'Let me check' — just call the tool.\n"
    "4. For all other questions, answer directly.\n\n"
    "EXAMPLE:\n"
    "User: show current stock\n"
    "You: sparepartspro_query(\"show current stock levels for all parts\")\n\n"
    "User: what are the top selling parts\n"
    "You: sparepartspro_query(\"what are the top selling parts\")"
)


class ContextPruner:
    def __init__(
        self,
        store:  FTS5Store,
        session_id: str,
        brain: BrainStore | None = None
    ):
        self.store      = store
        self.session_id = session_id
        self.brain      = brain

    async def build(self, new_content: str, full_history: list[dict]) -> list[dict]:
        """
        Returns a token-bounded message list:
          [system + brain_memory] + [fts5_recalled] + [recent_tail] + [new_user_msg]
        """
        # Build system prompt — inject brain memory if available
        system_content = BASE_SYSTEM_PROMPT
        if self.brain:
            mem_block = await self.brain.build_memory_block()
            if mem_block:
                system_content = system_content + "\n\n" + mem_block

        system   = [{"role": "system", "content": system_content}]
        recent   = full_history[-RECENT_MSGS_KEEP:]
        recalled = await self._recall(new_content, exclude=recent)

        budget  = CONTEXT_BUDGET - self._tokens(system)
        context = self._fit(recalled + recent, budget)
        # Compress context to save tokens before sending to LLM
        context = compress_messages(context, max_tokens=3800)
        return system + context + [{"role": "user", "content": new_content}]

    async def _recall(self, query: str, exclude: list[dict]) -> list[dict]:
        exclude_set = {m["content"] for m in exclude}
        rows = await self.store.search(self.session_id, query, limit=10)
        return [
            {"role": r["role"], "content": r["content"]}
            for r in rows
            if r["content"] not in exclude_set
        ]

    def _fit(self, messages: list[dict], budget: int) -> list[dict]:
        """Greedy-drop oldest messages until within token budget."""
        msgs = list(messages)
        while msgs and self._tokens(msgs) > budget:
            msgs.pop(0)
        return msgs

    def _tokens(self, messages: list[dict]) -> int:
        return sum(len(enc.encode(m.get("content", ""))) for m in messages)
