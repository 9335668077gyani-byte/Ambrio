# ambrio/router/erp/schema_context.py
"""
SparePartsPro schema context injected into the NL-to-SQL prompt.
Auto-generated from the live DB schema — update if tables change.
"""

SCHEMA_CONTEXT = """
DATABASE: SparePartsPro ERP (SQLite, read-only)
CURRENCY: Indian Rupee (INR)

TABLE: customers
  customer_id    TEXT PK
  name           TEXT   -- customer full name
  phone          TEXT
  email          TEXT
  address        TEXT
  gstin          TEXT   -- GST number
  loyalty_points INTEGER
  created_at     TEXT

TABLE: invoices
  invoice_id     TEXT PK
  customer_name  TEXT
  customer_phone TEXT
  reg_no         TEXT   -- vehicle registration number
  total_amount   REAL   -- total invoice amount in INR
  discount       REAL
  date           TEXT   -- invoice date (YYYY-MM-DD)
  json_items     TEXT   -- JSON array of line items
  items_count    INTEGER
  customer_gstin TEXT
  payment_cash   REAL
  payment_upi    REAL
  payment_due    REAL   -- outstanding balance
  payment_mode   TEXT   -- CASH / UPI / CREDIT / MIXED

TABLE: parts
  part_id        TEXT PK
  part_name      TEXT
  description    TEXT
  unit_price     REAL
  qty            INTEGER  -- current stock
  rack_number    TEXT
  reorder_level  INTEGER
  vendor_name    TEXT
  category       TEXT
  hsn_code       TEXT
  gst_rate       REAL     -- GST % (5 / 12 / 18 / 28)
  brand          TEXT
  model_no       TEXT
  mrp            REAL     -- maximum retail price
  avg_landing_cost REAL

TABLE: sales
  id             INTEGER PK
  invoice_id     TEXT FK→invoices.invoice_id
  part_id        TEXT FK→parts.part_id
  quantity       INTEGER
  price_at_sale  REAL
  sale_date      TEXT
  cogs           REAL     -- cost of goods sold

TABLE: purchase_orders (PO)
  po_id          TEXT PK
  supplier_name  TEXT
  order_date     TEXT
  status         TEXT     -- PENDING / RECEIVED / PARTIAL
  total_amount   REAL
  paid_amount    REAL
  due_amount     REAL
  payment_status TEXT

TABLE: vendors
  id             INTEGER PK
  name           TEXT
  phone          TEXT
  gstin          TEXT
  discount       REAL     -- vendor discount %

TABLE: returns
  return_id      INTEGER PK
  invoice_id     TEXT
  part_id        TEXT
  quantity       INTEGER
  refund_amount  REAL
  return_date    TEXT
  reason         TEXT

TABLE: users
  id             INTEGER PK
  username       TEXT
  role           TEXT     -- admin / staff
  last_login     TEXT
  is_active      INTEGER

USEFUL QUERY PATTERNS:
- Revenue today:     SELECT SUM(total_amount) FROM invoices WHERE date = date('now')
- Low stock parts:   SELECT part_name, qty, reorder_level FROM parts WHERE qty <= reorder_level
- Top selling:       SELECT part_id, SUM(quantity) qty FROM sales GROUP BY part_id ORDER BY qty DESC
- Due invoices:      SELECT invoice_id, customer_name, payment_due FROM invoices WHERE payment_due > 0
- Monthly revenue:   SELECT strftime('%Y-%m', date) m, SUM(total_amount) FROM invoices GROUP BY m
"""

# Tables that are safe to query (no PII passwords or internal config)
ALLOWED_TABLES = {
    "customers", "invoices", "parts", "sales", "purchase_orders",
    "po_items", "vendors", "returns", "loyalty_history",
    "payment_history", "warranty_records", "warranty_claims",
    "supplier_catalogs", "supplier_price_history"
}

BLOCKED_TABLES = {"users", "settings", "shop_config"}
