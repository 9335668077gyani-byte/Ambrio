"""
seed_test_data.py - Adds sample data to SparePartsPro DB for testing Ambrio ERP queries.
Run once: .venv\\Scripts\\python.exe seed_test_data.py
"""
import sqlite3, os, json
from datetime import datetime, timedelta
import random

DB = os.path.join(os.environ.get("APPDATA", ""), "SparePartsPro", "spare_parts.db")
print(f"Seeding: {DB}")

conn = sqlite3.connect(DB)

# Get actual tables first
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
print(f"Tables found: {sorted(tables)}")

# ── Parts ──────────────────────────────────────────────────────────────────
parts_data = [
    ("P001", "Brake Pad Set",    850.0,   5, 10, "Brakes",    "TVS",    18.0, 120.0),
    ("P002", "Oil Filter",       120.0,  25, 20, "Filters",   "Bosch",  18.0,  70.0),
    ("P003", "Air Filter",       200.0,   2,  5, "Filters",   "Bosch",  18.0, 110.0),
    ("P004", "Spark Plug Set",   350.0,  40, 15, "Ignition",  "NGK",    18.0, 180.0),
    ("P005", "Engine Oil 1L",    280.0,   8,  5, "Lubricants","Castrol", 12.0, 200.0),
    ("P006", "Clutch Plate",    1200.0,   3, 10, "Drivetrain","Honda",   18.0, 800.0),
    ("P007", "Chain Sprocket",   450.0,  15,  8, "Drivetrain","TVS",    18.0, 280.0),
    ("P008", "Front Tyre 90/90", 900.0,   6,  5, "Tyres",     "MRF",     5.0, 650.0),
    ("P009", "Rear Tyre 100/80",1100.0,   4,  5, "Tyres",     "MRF",     5.0, 790.0),
    ("P010", "Battery 12V",     1800.0,   0,  3, "Electrical","Amaron",  18.0,1200.0),
]

conn.executemany("""
    INSERT OR REPLACE INTO parts
      (part_id, part_name, unit_price, qty, reorder_level, category, brand, gst_rate, avg_landing_cost)
    VALUES (?,?,?,?,?,?,?,?,?)
""", parts_data)
print(f"  parts seeded: {len(parts_data)}")

# ── Invoices + Sales ──────────────────────────────────────────────────────
today    = datetime.now()
invoices = []
sales    = []
inv_num  = 1000

customer_names  = ["Ramesh Kumar", "Priya Devi", "Mohammed Ali", "Sunita Sharma", "Arjun Reddy"]
customer_phones = ["9876543210",   "9123456789", "9988776655",   "9800001111",    "9700002222"]

for days_ago in range(30):
    date = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    for _ in range(random.randint(1, 3)):
        inv_num   += 1
        ci        = random.randint(0, len(customer_names) - 1)
        part      = random.choice(parts_data)
        qty       = random.randint(1, 4)
        price     = part[2]
        gst_rate  = part[7]
        total     = round(qty * price * (1 + gst_rate / 100), 2)
        due       = round(total * random.choice([0, 0, 0, 0.25]), 2)
        mode      = random.choice(["CASH", "UPI", "CREDIT", "MIXED"])
        items     = json.dumps([{"part_id": part[0], "name": part[1], "qty": qty, "price": price}])

        invoices.append((
            f"INV{inv_num}",
            customer_names[ci],
            customer_phones[ci],
            random.choice(["Honda Activa", "TVS Jupiter", "Bajaj Pulsar", "Hero Splendor"]),
            f"TN{inv_num:02d}BCD",
            total,
            0.0,
            date,
            items,
            1,
            None,
            total - due,
            due,
            due,
            mode
        ))

        sales.append((
            f"INV{inv_num}",
            part[0],
            qty,
            price,
            date,
            round(qty * part[8], 2)
        ))

conn.executemany("""
    INSERT OR REPLACE INTO invoices
      (invoice_id, customer_name, mobile, vehicle_model, reg_no,
       total_amount, discount, date, json_items, items_count, customer_gstin,
       payment_cash, payment_upi, payment_due, payment_mode)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", invoices)

conn.executemany("""
    INSERT INTO sales
      (invoice_id, part_id, quantity, price_at_sale, sale_date, cogs)
    VALUES (?,?,?,?,?,?)
""", sales)

conn.commit()

# ── Verify ────────────────────────────────────────────────────────────────
print(f"\n  parts:    {conn.execute('SELECT COUNT(*) FROM parts').fetchone()[0]} rows")
print(f"  invoices: {conn.execute('SELECT COUNT(*) FROM invoices').fetchone()[0]} rows")
print(f"  sales:    {conn.execute('SELECT COUNT(*) FROM sales').fetchone()[0]} rows")

rev = conn.execute("SELECT ROUND(SUM(total_amount),2) FROM invoices").fetchone()[0]
print(f"  30-day revenue: Rs.{rev}")

low = conn.execute("SELECT COUNT(*) FROM parts WHERE qty <= reorder_level").fetchone()[0]
print(f"  low-stock parts: {low}")

dues = conn.execute("SELECT ROUND(SUM(payment_due),2) FROM invoices WHERE payment_due > 0").fetchone()[0]
print(f"  outstanding dues: Rs.{dues}")

conn.close()
print("\nDone! Restart Ambrio to query live ERP data.")
