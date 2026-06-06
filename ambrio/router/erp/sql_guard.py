# ambrio/router/erp/sql_guard.py
"""
SQL Guard — validates generated SQL before executing against SparePartsPro.

Three layers of protection:
  1. Statement type — only SELECT allowed
  2. Table allowlist — blocks users/settings/shop_config
  3. Dangerous pattern scan — blocks DROP, DELETE, pragma writes, etc.
"""
import re
from .schema_context import ALLOWED_TABLES, BLOCKED_TABLES

# Patterns that are never allowed regardless of table
DANGEROUS_PATTERNS = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|CREATE|ALTER|ATTACH|DETACH|PRAGMA\s+\w+=|"
    r"VACUUM|REINDEX|ANALYZE|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE
)

# Subquery / stacked statement separators
STACKED_STMT = re.compile(r";\s*\w", re.IGNORECASE)


class SQLGuardError(ValueError):
    pass


def validate(sql: str) -> str:
    """
    Validate and clean SQL. Returns normalized SQL or raises SQLGuardError.
    """
    sql = sql.strip().rstrip(";")

    # Must be a single SELECT
    if not sql.upper().lstrip().startswith("SELECT"):
        raise SQLGuardError("Only SELECT statements are permitted")

    if STACKED_STMT.search(sql):
        raise SQLGuardError("Stacked statements are not permitted")

    if DANGEROUS_PATTERNS.search(sql):
        raise SQLGuardError("Dangerous SQL pattern detected")

    # Check for blocked table names
    sql_upper = sql.upper()
    for blocked in BLOCKED_TABLES:
        pattern = r"\b" + blocked.upper() + r"\b"
        if re.search(pattern, sql_upper):
            raise SQLGuardError(f"Access to table '{blocked}' is not permitted")

    return sql


def extract_sql(text: str) -> str | None:
    """
    Extract the first SQL SELECT statement from LLM output.
    Handles markdown code blocks and inline SQL.
    """
    # Try markdown code block first
    block = re.search(r"```(?:sql)?\s*\n?(SELECT[\s\S]+?)\n?```", text, re.IGNORECASE)
    if block:
        return block.group(1).strip()

    # Try inline SELECT
    inline = re.search(r"(SELECT\s[\s\S]+?)(?:;|$)", text, re.IGNORECASE)
    if inline:
        return inline.group(1).strip()

    return None
