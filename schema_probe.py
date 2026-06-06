import sqlite3, os, json

db_path = os.path.join(os.environ.get("APPDATA", ""), "SparePartsPro", "spare_parts.db")
print(f"DB path: {db_path}")
print(f"Exists: {os.path.exists(db_path)}")

if not os.path.exists(db_path):
    print("DB not found")
    exit(0)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get all tables
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print(f"\nTables ({len(tables)}): {tables}")

# Get schema for each table
for table in tables:
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = [(r["name"], r["type"]) for r in cur.fetchall()]
    cur2 = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
    count = cur2.fetchone()[0]
    print(f"\n  {table} ({count} rows):")
    for name, typ in cols:
        print(f"    {name:30} {typ}")

conn.close()
