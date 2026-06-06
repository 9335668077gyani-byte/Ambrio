# tests/unit/test_nl_to_sql.py
"""
Tests for NL-to-SQL engine.
Mocks the Ollama LLM calls so no live model is needed.
Tests the full pipeline: NL → SQL generate → validate → execute → answer.
"""
import pytest, json, os, tempfile, sqlite3
from unittest.mock import MagicMock, patch, AsyncMock

from ambrio.router.erp.nl_to_sql  import ERPQueryEngine
from ambrio.router.erp.sql_guard  import SQLGuardError


# ── Fixture: in-memory SparePartsPro-like DB ──────────────────────────────────
@pytest.fixture
def fake_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "spare_parts.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE parts (
            part_id TEXT PRIMARY KEY,
            part_name TEXT,
            qty INTEGER,
            unit_price REAL,
            reorder_level INTEGER,
            category TEXT
        );
        INSERT INTO parts VALUES ('P001', 'Brake Pad Set', 5, 850.0, 10, 'Brakes');
        INSERT INTO parts VALUES ('P002', 'Oil Filter',   25, 120.0, 20, 'Filters');
        INSERT INTO parts VALUES ('P003', 'Air Filter',    2, 200.0,  5, 'Filters');

        CREATE TABLE invoices (
            invoice_id TEXT PRIMARY KEY,
            customer_name TEXT,
            total_amount REAL,
            date TEXT,
            payment_due REAL
        );
        INSERT INTO invoices VALUES ('INV001', 'Ram Kumar', 5000.0, date('now'), 0);
        INSERT INTO invoices VALUES ('INV002', 'Priya Devi', 3200.0, date('now'), 1500);
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr("ambrio.router.erp.nl_to_sql.SPARE_DB", db_path)
    return db_path


def make_engine_with_mock_llm(sql_response: str, answer_response: str = "Here is your answer."):
    """Create ERPQueryEngine with mocked Ollama that returns given SQL then answer."""
    call_count = [0]

    async def fake_stream(messages, tools=None):
        response = sql_response if call_count[0] == 0 else answer_response
        call_count[0] += 1
        yield {"done": False, "message": {"content": response}}
        yield {"done": True}

    mock_ollama = MagicMock()
    mock_ollama.stream = fake_stream
    engine = ERPQueryEngine(mock_ollama)
    return engine


@pytest.mark.asyncio
async def test_nl_query_returns_answer(fake_db):
    engine = make_engine_with_mock_llm(
        sql_response   = "SELECT part_name, qty FROM parts WHERE qty < 10",
        answer_response= "You have 2 parts below reorder level: Brake Pad Set (5) and Air Filter (2)."
    )
    result = await engine.query("Which parts are low on stock?")
    assert result["error"]  is None
    assert result["sql"]    is not None
    assert "SELECT" in result["sql"].upper()
    assert len(result["rows"]) == 2
    assert "Brake Pad Set" in result["rows"][0].values() or "Air Filter" in result["rows"][1].values()


@pytest.mark.asyncio
async def test_nl_query_blocks_dangerous_sql(fake_db):
    engine = make_engine_with_mock_llm(
        sql_response = "DELETE FROM parts WHERE 1=1",
    )
    result = await engine.query("Delete all parts")
    assert result["error"] is not None
    assert result["rows"]  == []


@pytest.mark.asyncio
async def test_nl_query_blocks_users_table(fake_db):
    engine = make_engine_with_mock_llm(
        sql_response = "SELECT username, password FROM users",
    )
    result = await engine.query("Show me all passwords")
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_execute_returns_rows(fake_db):
    engine = ERPQueryEngine(MagicMock())
    rows, err = await engine._execute("SELECT invoice_id, total_amount FROM invoices")
    assert err  is None
    assert len(rows) == 2
    assert rows[0]["total_amount"] == 5000.0


@pytest.mark.asyncio
async def test_execute_returns_error_on_bad_sql(fake_db):
    engine = ERPQueryEngine(MagicMock())
    rows, err = await engine._execute("SELECT * FROM nonexistent_table_xyz")
    assert err is not None
    assert rows == []


@pytest.mark.asyncio
async def test_db_not_available():
    engine = ERPQueryEngine(MagicMock())
    engine._db_available = False
    result = await engine.query("total revenue today")
    assert "not available" in result["answer"].lower()
