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
    Query the SparePartsPro ERP database (N.A. MOTORS shop) using natural language.

    DATABASE SCHEMA (use these EXACT table and column names):

    TABLE: parts
      part_id, part_name, description, unit_price, qty, rack_number, col_number,
      reorder_level, vendor_name, compatibility, category, added_date,
      hsn_code, gst_rate, avg_landing_cost, brand, model_no, warranty_months,
      unit_of_measure, barcode, mrp
      REAL CATEGORIES: 'Brakes', 'Drivetrain', 'Electrical', 'Filters',
                       'Ignition', 'Lubricants', 'Tyres'
      NOTE: There is NO 'Electronics' category. Use 'Electrical' instead.

    TABLE: invoices
      invoice_id, customer_name, mobile, vehicle_model, reg_no, total_amount,
      discount, date, json_items, items_count, payment_cash, payment_upi,
      payment_due, payment_mode

    TABLE: sales
      id, invoice_id, part_id, quantity, price_at_sale, sale_date, cogs

    TABLE: vendors
      id, name, rep_name, phone, address, gstin, notes, discount

    TABLE: purchase_orders
      po_id, supplier_name, order_date, status, total_amount, paid_amount,
      due_amount, payment_status

    TABLE: po_items
      id, po_id, part_id, part_name, qty_ordered, qty_received, received_cost,
      ordered_price, hsn_code, gst_rate

    TABLE: returns
      return_id, invoice_id, part_id, quantity, refund_amount, return_date, reason

    TABLE: expenses
      id, title, amount, category, date

    EXAMPLE QUERIES:
      - 'total sales today'         -> SUM(total_amount) FROM invoices WHERE date=today
      - 'low stock parts'           -> SELECT * FROM parts WHERE qty < reorder_level
      - 'top selling parts'         -> JOIN sales+parts GROUP BY part_id ORDER BY SUM(quantity)
      - 'Electrical parts'          -> SELECT * FROM parts WHERE category='Electrical'
      - 'pending purchase orders'   -> SELECT * FROM purchase_orders WHERE status='Pending'
    """
    global _engine
    if not _engine:
        _engine = ERPQueryEngine()
    return await _engine.query(question)


@tool()
async def sparepartspro_sql(sql: str) -> dict:
    """
    Run a raw READ-ONLY SQL SELECT against the SparePartsPro database (N.A. MOTORS).

    REAL TABLE NAMES: parts, invoices, sales, vendors, purchase_orders, po_items,
                      returns, expenses, warranty_records, hsn_master

    REAL CATEGORIES IN parts TABLE:
      'Brakes', 'Drivetrain', 'Electrical', 'Filters', 'Ignition', 'Lubricants', 'Tyres'
      WARNING: 'Electronics' does NOT exist -- use 'Electrical'

    BLOCKED TABLES (never query): users, settings, shop_config, ambrio_settings

    EXAMPLE:
      SELECT part_name, qty, unit_price FROM parts WHERE category='Electrical'
      SELECT customer_name, total_amount, date FROM invoices ORDER BY date DESC LIMIT 10
      SELECT p.part_name, SUM(s.quantity) as sold FROM sales s
        JOIN parts p ON s.part_id=p.part_id GROUP BY p.part_id ORDER BY sold DESC LIMIT 5
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
