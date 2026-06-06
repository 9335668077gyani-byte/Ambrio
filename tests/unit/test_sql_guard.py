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
