# ambrio/router/erp/nl_to_sql.py
"""
NL-to-SQL engine for SparePartsPro ERP.

Flow:
  1. User asks a natural language question about the business
  2. Build prompt with schema context + question
  3. Call Ollama → get SQL
  4. Validate SQL with SQLGuard
  5. Execute against SparePartsPro DB
  6. Format results as human-readable answer (second LLM call)

Inspired by Hermes tool-use patterns — uses a two-shot approach:
  Shot 1: NL → SQL
  Shot 2: rows + question → natural language answer
"""
import asyncio
import re as _re
import aiosqlite, os, logging, json
from .schema_context import SCHEMA_CONTEXT
from .sql_guard      import validate, extract_sql, SQLGuardError
from ..ollama_client import OllamaClient

log = logging.getLogger(__name__)

SPARE_DB = os.path.join(
    os.environ.get("APPDATA", ""), "SparePartsPro", "spare_parts.db"
)

_QUERY_TIMEOUT_SECS: float = 3.0   # G2: 3000ms hard cap on SQL execution
_MAX_ROWS:           int   = 50    # G2: absolute row ceiling


def _inject_limit(sql: str) -> str:
    """Ensure the outermost SELECT has LIMIT <= _MAX_ROWS.

    Rules:
    - No LIMIT present  → append LIMIT 50
    - LIMIT N where N > 50 → replace with LIMIT 50
    - LIMIT N where N <= 50 → leave unchanged
    """
    sql = sql.strip().rstrip(";").rstrip()
    # Match a LIMIT clause at the very end of the string (outer query only)
    outer_limit = _re.search(r'\bLIMIT\s+(\d+)\s*$', sql, _re.IGNORECASE)
    if outer_limit:
        n = int(outer_limit.group(1))
        if n > _MAX_ROWS:
            sql = sql[:outer_limit.start()] + f"LIMIT {_MAX_ROWS}"
        # else: already within budget — leave as-is
    else:
        sql = f"{sql} LIMIT {_MAX_ROWS}"
    return sql

NL_TO_SQL_PROMPT = """\
You are an expert SQLite query generator for a spare parts shop ERP database.

{schema}

TASK: Write a single SQLite SELECT query to answer the user's question.
Rules:
- Output ONLY the SQL query, no explanation.
- Use only tables listed above.
- Never query users, settings, or shop_config tables.
- Limit results to 50 rows unless the user asks for all.
- Use strftime for date operations.
- For amounts, round to 2 decimal places.

USER QUESTION: {question}

SQL:"""

ANSWER_PROMPT = """\
You are Ambrio, an AI assistant for a spare parts shop.
The user asked: "{question}"

The database returned these results:
{results}

Give a clear, friendly, concise answer in plain English. 
Include relevant numbers. If results are empty, say so helpfully.
Do NOT show raw SQL or table names to the user."""


class ERPQueryEngine:
    def __init__(self, ollama: OllamaClient | None = None):
        self.ollama = ollama or OllamaClient()
        self._db_available = os.path.exists(SPARE_DB)

    async def query(self, question: str) -> dict:
        """
        Full NL-to-SQL-to-answer pipeline.
        Returns: {"answer": str, "sql": str, "rows": list, "error": str|None}
        """
        if not self._db_available:
            return {
                "answer": "SparePartsPro database is not available. Is the app installed?",
                "sql":    None,
                "rows":   [],
                "error":  "DB not found"
            }

        # Shot 1: Generate SQL
        sql_raw = await self._generate_sql(question)
        if not sql_raw:
            return {"answer": "I couldn't generate a query for that question.", "sql": None, "rows": [], "error": "no SQL generated"}

        # Extract SQL from LLM output (handles markdown code blocks)
        sql = extract_sql(sql_raw) or sql_raw

        # Validate
        try:
            sql = validate(sql)
        except SQLGuardError as e:
            log.warning(f"SQL guard rejected: {e} | SQL: {sql}")
            return {"answer": f"I can't run that query: {e}", "sql": sql, "rows": [], "error": str(e)}

        # Execute
        rows, exec_error = await self._execute(sql)
        if exec_error:
            return {"answer": f"Query error: {exec_error}", "sql": sql, "rows": [], "error": exec_error}

        # Shot 2: Generate natural language answer
        answer = await self._generate_answer(question, rows, sql)
        return {"answer": answer, "sql": sql, "rows": rows, "error": None}

    async def _generate_sql(self, question: str) -> str | None:
        prompt = NL_TO_SQL_PROMPT.format(schema=SCHEMA_CONTEXT, question=question)
        response = ""
        try:
            async for chunk in self.ollama.stream([{"role": "user", "content": prompt}]):
                if chunk.get("done"):
                    break
                response += chunk.get("message", {}).get("content", "")
        except Exception as e:
            log.error(f"SQL generation failed: {e}")
            return None
        return response.strip()

    async def _execute(self, sql: str) -> tuple[list[dict], str | None]:
        """Execute validated SQL. Injects LIMIT and enforces 3s timeout."""
        sql = _inject_limit(sql)  # G2: force LIMIT before every execution
        try:
            async with asyncio.timeout(_QUERY_TIMEOUT_SECS):   # G2: 3000ms cap
                async with aiosqlite.connect(SPARE_DB) as conn:
                    conn.row_factory = aiosqlite.Row
                    await conn.execute("PRAGMA query_only = ON")
                    cur  = await conn.execute(sql)
                    rows = await cur.fetchall()
            return [dict(r) for r in rows[:_MAX_ROWS]], None
        except TimeoutError:
            err = f"Query timed out after {_QUERY_TIMEOUT_SECS}s"
            log.warning("[ERP] %s | sql=%s", err, sql[:120])
            return [], err
        except Exception as e:
            return [], str(e)

    async def _generate_answer(self, question: str, rows: list[dict], sql: str) -> str:
        # Format rows compactly
        if not rows:
            result_text = "No records found."
        elif len(rows) == 1:
            result_text = json.dumps(rows[0], indent=2, default=str)
        else:
            # Tabular summary
            keys = list(rows[0].keys())
            lines = [" | ".join(keys)]
            lines.append("-" * len(lines[0]))
            for row in rows[:20]:  # cap at 20 for the answer prompt
                lines.append(" | ".join(str(row.get(k, "")) for k in keys))
            if len(rows) > 20:
                lines.append(f"... and {len(rows) - 20} more rows")
            result_text = "\n".join(lines)

        prompt = ANSWER_PROMPT.format(question=question, results=result_text)
        response = ""
        try:
            async for chunk in self.ollama.stream([{"role": "user", "content": prompt}]):
                if chunk.get("done"):
                    break
                response += chunk.get("message", {}).get("content", "")
        except Exception as e:
            log.error(f"Answer generation failed: {e}")
            # Fallback: just show the raw rows
            response = f"Found {len(rows)} record(s):\n{result_text}"
        return response.strip() or f"Found {len(rows)} record(s)."
