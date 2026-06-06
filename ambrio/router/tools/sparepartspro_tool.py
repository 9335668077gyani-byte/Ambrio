# ambrio/router/tools/sparepartspro_tool.py
import aiosqlite, os
from ..tool_registry import tool

SPARE_DB = os.path.join(
    os.environ.get("APPDATA", ""), "SparePartsPro", "spare_parts.db"
)

@tool()
async def sparepartspro_query(sql: str) -> dict:
    """Run a READ-ONLY SELECT query against the SparePartsPro database. Only SELECT statements are permitted."""
    sql_clean = sql.strip()
    if not sql_clean.upper().startswith("SELECT"):
        return {"error": "Only SELECT queries are permitted"}
    if not os.path.exists(SPARE_DB):
        return {"error": f"SparePartsPro database not found at: {SPARE_DB}"}
    try:
        async with aiosqlite.connect(SPARE_DB) as c:
            c.row_factory = aiosqlite.Row
            cur = await c.execute(sql_clean)
            rows = await cur.fetchall()
        return {"rows": [dict(r) for r in rows[:100]]}  # cap at 100 rows
    except Exception as e:
        return {"error": str(e)}
