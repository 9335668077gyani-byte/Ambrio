# tests/unit/test_sql_guard.py
import pytest
from ambrio.router.erp.sql_guard import validate, extract_sql, SQLGuardError


def test_valid_select():
    sql = validate("SELECT part_name, qty FROM parts WHERE qty < 10")
    assert sql.startswith("SELECT")


def test_rejects_non_select():
    with pytest.raises(SQLGuardError, match="Only SELECT"):
        validate("DELETE FROM invoices WHERE 1=1")


def test_rejects_update():
    with pytest.raises(SQLGuardError):
        validate("UPDATE parts SET qty = 0")


def test_rejects_drop():
    with pytest.raises(SQLGuardError):
        validate("SELECT * FROM parts; DROP TABLE parts")


def test_rejects_blocked_table_users():
    with pytest.raises(SQLGuardError, match="users"):
        validate("SELECT username, password FROM users")


def test_rejects_blocked_table_settings():
    with pytest.raises(SQLGuardError, match="settings"):
        validate("SELECT * FROM settings")


def test_rejects_pragma_write():
    with pytest.raises(SQLGuardError):
        validate("PRAGMA journal_mode=WAL")


def test_strips_trailing_semicolon():
    sql = validate("SELECT COUNT(*) FROM invoices;")
    assert not sql.endswith(";")


def test_extract_from_markdown_block():
    text = "Here is the query:\n```sql\nSELECT * FROM parts\n```"
    sql  = extract_sql(text)
    assert sql == "SELECT * FROM parts"


def test_extract_inline_sql():
    text = "The answer is: SELECT SUM(total_amount) FROM invoices WHERE date = date('now')"
    sql  = extract_sql(text)
    assert "SUM" in sql


def test_extract_returns_none_when_no_sql():
    sql = extract_sql("I don't know the answer.")
    assert sql is None


def test_rejects_stacked_statements():
    with pytest.raises(SQLGuardError, match="Stacked"):
        validate("SELECT 1; SELECT 2")


# ── G2: LIMIT injection tests ─────────────────────────────────────────────────

def test_inject_limit_adds_limit_when_missing():
    """Query without LIMIT gets LIMIT 50 appended."""
    from ambrio.router.erp.nl_to_sql import _inject_limit
    sql = "SELECT part_name, qty FROM parts WHERE qty < 10"
    result = _inject_limit(sql)
    assert result.upper().endswith("LIMIT 50")


def test_inject_limit_preserves_existing_lower_limit():
    """Query with LIMIT 5 stays at LIMIT 5."""
    from ambrio.router.erp.nl_to_sql import _inject_limit
    sql = "SELECT * FROM parts LIMIT 5"
    result = _inject_limit(sql)
    assert "LIMIT 5" in result.upper()
    assert result.upper().count("LIMIT") == 1


def test_inject_limit_caps_large_limit():
    """Query with LIMIT 1000 gets capped to LIMIT 50."""
    from ambrio.router.erp.nl_to_sql import _inject_limit
    sql = "SELECT * FROM parts LIMIT 1000"
    result = _inject_limit(sql)
    assert "LIMIT 50" in result.upper()


def test_inject_limit_handles_limit_in_subquery():
    """LIMIT in subquery — outer query still gets LIMIT 50 if absent."""
    from ambrio.router.erp.nl_to_sql import _inject_limit
    sql = "SELECT * FROM (SELECT id FROM parts LIMIT 100)"
    result = _inject_limit(sql)
    assert result.upper().rstrip().endswith("LIMIT 50")


# ── G2: Timeout tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_returns_error_on_timeout(tmp_path):
    """_execute() returns ([], error_str) if query hangs longer than 3s."""
    import asyncio
    import aiosqlite
    from unittest.mock import patch, MagicMock, AsyncMock
    from ambrio.router.erp.nl_to_sql import ERPQueryEngine

    db = tmp_path / "test.db"
    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute("CREATE TABLE parts (id INTEGER PRIMARY KEY, name TEXT)")
        await conn.commit()

    engine = ERPQueryEngine.__new__(ERPQueryEngine)
    engine.ollama = None
    engine._db_available = True

    # Create an async context manager whose __aenter__ hangs forever
    class HangingConnCtx:
        async def __aenter__(self):
            await asyncio.sleep(999)

        async def __aexit__(self, *args):
            pass

    with patch("ambrio.router.erp.nl_to_sql.SPARE_DB", str(db)):
        with patch("ambrio.router.erp.nl_to_sql._QUERY_TIMEOUT_SECS", 0.05):
            with patch("aiosqlite.connect", return_value=HangingConnCtx()):
                rows, err = await engine._execute("SELECT * FROM parts")
    assert err is not None
    assert "timeout" in err.lower() or "timed out" in err.lower()
    assert rows == []


@pytest.mark.asyncio
async def test_execute_completes_fast_query(tmp_path):
    """_execute() succeeds on a normal fast query."""
    import aiosqlite
    from unittest.mock import patch
    from ambrio.router.erp.nl_to_sql import ERPQueryEngine

    db = tmp_path / "test.db"
    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute("CREATE TABLE parts (id INTEGER PRIMARY KEY, name TEXT)")
        await conn.execute("INSERT INTO parts VALUES (1, 'brake pad')")
        await conn.commit()

    engine = ERPQueryEngine.__new__(ERPQueryEngine)
    engine.ollama = None
    engine._db_available = True

    with patch("ambrio.router.erp.nl_to_sql.SPARE_DB", str(db)):
        rows, err = await engine._execute("SELECT * FROM parts LIMIT 50")
    assert err is None
    assert len(rows) == 1
    assert rows[0]["name"] == "brake pad"
