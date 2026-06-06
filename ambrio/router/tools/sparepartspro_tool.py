# ambrio/router/tools/sparepartspro_tool.py
"""
SparePartsPro ERP tool — two modes:

  1. Natural language query (preferred):
     sparepartspro_query(question="What are my top 5 selling parts this month?")
     → calls ERPQueryEngine: NL → SQL → execute → NL answer

  2. Raw SQL (fallback, still guarded):
     sparepartspro_query(sql="SELECT part_name, qty FROM parts WHERE qty < 10")
     → runs validated SQL directly, returns rows as JSON

The tool is registered via @tool() and dispatched by the ToolRegistry.
"""
import json
from ..tool_registry import tool
from ..erp.nl_to_sql  import ERPQueryEngine
from ..erp.sql_guard  import validate, SQLGuardError

_engine: ERPQueryEngine | None = None


def init_erp_tool(engine: ERPQueryEngine) -> None:
    global _engine
    _engine = engine


@tool()
async def sparepartspro_query(question: str) -> dict:
    """
    Query the SparePartsPro ERP database using natural language.
    Ask anything about invoices, parts inventory, sales, customers, purchase orders, or vendors.
    Examples: 'total sales today', 'parts below reorder level', 'top 10 selling parts this month'.
    """
    global _engine
    if not _engine:
        _engine = ERPQueryEngine()
    return await _engine.query(question)


@tool()
async def sparepartspro_sql(sql: str) -> dict:
    """
    Run a raw READ-ONLY SQL SELECT against the SparePartsPro database.
    Only use this when you need precise control over the query.
    Never query: users, settings, shop_config tables.
    """
    global _engine
    if not _engine:
        _engine = ERPQueryEngine()
    try:
        sql = validate(sql)
    except SQLGuardError as e:
        return {"error": str(e), "rows": []}
    rows, err = await _engine._execute(sql)
    if err:
        return {"error": err, "rows": []}
    return {"rows": rows, "count": len(rows)}
