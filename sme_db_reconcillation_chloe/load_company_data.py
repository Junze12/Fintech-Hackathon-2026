"""
Loads your company CSVs into a fresh SQLite database, runs the reconciliation,
and exports every table and view to an Excel workbook for viewing.
 
Usage:  python3 load_company_data.py
Needs:  pandas (and openpyxl for the Excel file) - both come with Anaconda.
 
The CSVs in data/ are the source of truth. Edit them, save, and re-run this script;
company.db and cashflow_report.xlsx are rebuilt from scratch each time.
"""
import os, sqlite3
import pandas as pd
 
HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_FILE    = "dbschema.sql"      # change if your file has a different name
RECONCILE_FILE = "reconcile.sql"
DB_FILE        = os.path.join(HERE, "company.db")
EXCEL_FILE     = os.path.join(HERE, "cashflow_report.xlsx")
 
# Order matters: parents before children (foreign keys)
LOAD_ORDER = [
    "bank_account", "cf_category", "customer", "supplier",
    "sales_invoice", "supplier_bill", "loan", "fixed_asset",
    "ledger_cash_entry", "bank_statement_line",
    "supplier_statement", "supplier_statement_line",
]
 
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
conn = sqlite3.connect(DB_FILE)
conn.execute("PRAGMA foreign_keys = ON")
 
with open(os.path.join(HERE, SCHEMA_FILE)) as f:
    conn.executescript(f.read())
print("Created tables from", SCHEMA_FILE)
 
for table in LOAD_ORDER:
    path = os.path.join(HERE, "data", f"{table}.csv")
    if not os.path.exists(path):
        print(f"  skipped {table} (no data/{table}.csv)")
        continue
    # read everything as text; SQLite converts to numbers/dates using each column's type
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = df.replace("", None)
    if df.empty:
        print(f"  {table}: 0 rows")
        continue
    try:
        df.to_sql(table, conn, if_exists="append", index=False)
    except Exception as e:
        raise SystemExit(f"\nProblem loading data/{table}.csv:\n  {e}\n"
                         "Check column names, dates (YYYY-MM-DD), and that IDs it refers to exist.")
    print(f"  {table}: {len(df)} rows")
conn.commit()
 
with open(os.path.join(HERE, RECONCILE_FILE)) as f:
    conn.executescript(f.read())
conn.commit()
print("\nReconciliation done")
print("  matched pairs:", conn.execute("SELECT COUNT(*) FROM recon_match").fetchone()[0])
print("  exceptions:   ", conn.execute("SELECT COUNT(*) FROM recon_exception").fetchone()[0])
 
# ---- Export every table and view to Excel (most useful sheets first) ----
first = ["recon_exception", "v_unreconciled", "v_cashflow_summary", "v_cash_position",
         "v_invoice_balance", "v_bill_balance", "v_supplier_balance_check"]
objs = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")]
ordered = [o for o in first if o in objs] + [o for o in objs if o not in first]
 
try:
    with pd.ExcelWriter(EXCEL_FILE, engine="openpyxl") as xl:
        for name in ordered:
            df = pd.read_sql_query(f"SELECT * FROM {name}", conn)
            df.to_excel(xl, sheet_name=name[:31], index=False)
            ws = xl.sheets[name[:31]]
            for i, col in enumerate(df.columns, start=1):
                width = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)]) + 2
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(width, 60)
    print("\nExcel report written:", EXCEL_FILE)
except ModuleNotFoundError:
    out = os.path.join(HERE, "output"); os.makedirs(out, exist_ok=True)
    for name in ordered:
        pd.read_sql_query(f"SELECT * FROM {name}", conn).to_csv(os.path.join(out, f"{name}.csv"), index=False)
    print("\nopenpyxl not installed - wrote CSVs to", out)
conn.close()