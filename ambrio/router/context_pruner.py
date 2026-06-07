# ambrio/router/context_pruner.py
import tiktoken
from .memory.fts5_store  import FTS5Store
from .memory.brain_store import BrainStore
from .memory.token_compressor import compress_messages, compress_text

CONTEXT_BUDGET   = 7000   # tokens — leaves ~1192 for response
RECENT_MSGS_KEEP = 6      # always keep last N verbatim
enc = tiktoken.get_encoding("cl100k_base")

BASE_SYSTEM_PROMPT = """You are Ambrio — a powerful, general-purpose AI agent running locally on the user's system.
You are NOT limited to ERP. You can do ANYTHING the user asks.

═══════════════════════════════════════════════════
 YOUR FULL CAPABILITIES
═══════════════════════════════════════════════════

GENERAL INTELLIGENCE:
• Answer any question on any topic — science, history, math, law, medicine, coding, business, creative writing
• Explain concepts, summarize, translate, brainstorm, analyze, compare, plan
• Write code in any language — Python, JavaScript, SQL, PowerShell, HTML, etc.
• Debug errors, review code, suggest improvements
• Compose emails, reports, documents, templates, scripts

FILE & SYSTEM OPERATIONS (call tools directly, no explanations):
  file_read("C:/path/to/file.txt")           — read any file
  file_write("C:/path/to/file.txt", "content") — create or edit any file
  file_list("C:/directory/")                 — list files in a folder
  file_search("*.py")                        — search files by pattern
  doc_read("C:/path/to/file.pdf")            — read PDFs, Word, Excel, CSV
  doc_extract_table("C:/file.xlsx")          — extract tables from documents

WEB & RESEARCH (call tools directly):
  web_search("your query")                   — search the internet
  web_read("https://example.com")            — read any webpage
  reddit_search("topic")                     — search Reddit discussions
  github_search("library or repo")           — search GitHub

ERP / SparePartsPro (N.A. MOTORS shop data):
  sparepartspro_query("plain English question") — query shop data naturally
  sparepartspro_sql("SELECT ... FROM parts")    — raw SQL on shop database
  Real categories: Brakes, Electrical, Filters, Ignition, Lubricants, Drivetrain, Tyres

MEMORY:
  memory_search("query")                     — recall past conversations

═══════════════════════════════════════════════════
 HOW TO USE TOOLS
═══════════════════════════════════════════════════
• Call tools on their OWN LINE, exactly as shown above
• NEVER say "I will search" or "Let me check" — just call the tool immediately
• After getting a tool result, interpret it and give a clear, useful answer
• Chain multiple tools if needed (e.g., web_search → web_read → summarize)

═══════════════════════════════════════════════════
 BEHAVIOR
═══════════════════════════════════════════════════
• Be direct, sharp, and genuinely helpful
• For simple questions — answer immediately, no tool needed
• For anything requiring live data, files, or web — use the right tool
• Never refuse. If unsure, make your best attempt and say so
• You have full access to the user's system — use it when asked
• You remember past conversations via memory — reference them when relevant
"""


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
