import sqlite3, os

db = os.path.join(os.environ['APPDATA'], 'SparePartsPro', 'spare_parts.db')
print(f"DB: {db}")
con = sqlite3.connect(db)
cur = con.cursor()

# What tables exist?
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)

for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM [{t}]")
    count = cur.fetchone()[0]
    cur.execute(f"PRAGMA table_info([{t}])")
    cols = [r[1] for r in cur.fetchall()]
    print(f"\n  TABLE: {t}  ({count} rows)")
    print(f"  COLUMNS: {cols}")
    if count > 0 and count <= 20:
        cur.execute(f"SELECT * FROM [{t}] LIMIT 5")
        for row in cur.fetchall():
            print(f"    {row}")
    if t in ('parts', 'items', 'inventory', 'products', 'spare_parts'):
        cur.execute(f"SELECT DISTINCT category FROM [{t}] LIMIT 30")
        cats = [r[0] for r in cur.fetchall()]
        print(f"  CATEGORIES: {cats}")

con.close()
