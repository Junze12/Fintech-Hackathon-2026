-- SME Cashflow Database Schema
-- SQLite schema and reconciliation engine for the SME Cashflow application.
-- Sign convention: cash IN is positive; cash OUT is negative.
--
-- IMPORTANT:
-- 1. This script creates tables and views if they do not already exist.
-- 2. Reconciliation/exception checks run against the data currently in the database.
-- 3. If you change an existing table's structure, back up your database and recreate
--    it or write explicit ALTER TABLE migrations. IF NOT EXISTS does not alter old tables.

PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. REFERENCE / MASTER DATA
-- ============================================================

CREATE TABLE IF NOT EXISTS bank_account (
    account_number INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'SGD',
    opening_balance REAL NOT NULL DEFAULT 0.0
);

-- Maps cash movements to operating, investing, or financing activities.
CREATE TABLE IF NOT EXISTS cf_category (
    category_id INTEGER PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE,
    activity TEXT NOT NULL
        CHECK (activity IN ('OPERATING', 'INVESTING', 'FINANCING')),
    direction TEXT NOT NULL
        CHECK (direction IN ('IN', 'OUT'))
);

CREATE TABLE IF NOT EXISTS customer (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    contact_info TEXT,
    payment_terms_days INTEGER NOT NULL DEFAULT 30
        CHECK (payment_terms_days >= 0)
);

CREATE TABLE IF NOT EXISTS supplier (
    supplier_id INTEGER PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    contact_info TEXT,
    payment_terms_days INTEGER NOT NULL DEFAULT 30
        CHECK (payment_terms_days >= 0)
);

-- ============================================================
-- 2. SUBLEDGERS
-- ============================================================

-- Accounts Receivable (AR): customer sales invoices.
CREATE TABLE IF NOT EXISTS sales_invoice (
    invoice_id INTEGER PRIMARY KEY,
    invoice_no TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customer(customer_id),
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    total_amount NUMERIC NOT NULL CHECK (total_amount >= 0),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PAID', 'OVERDUE')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Accounts Payable (AP): supplier bills.
CREATE TABLE IF NOT EXISTS supplier_bill (
    bill_id INTEGER PRIMARY KEY,
    bill_no TEXT NOT NULL UNIQUE,
    supplier_id INTEGER NOT NULL REFERENCES supplier(supplier_id),
    supplier_invoice_no TEXT NOT NULL,
    bill_date DATE NOT NULL,
    due_date DATE NOT NULL,
    total_amount NUMERIC NOT NULL CHECK (total_amount >= 0),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PAID', 'OVERDUE')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (supplier_id, supplier_invoice_no)
);

-- Financing: loans.
CREATE TABLE IF NOT EXISTS loan (
    loan_id INTEGER PRIMARY KEY,
    loan_no TEXT NOT NULL UNIQUE,
    lender_name TEXT NOT NULL,
    loan_date DATE NOT NULL,
    principal_amount NUMERIC NOT NULL CHECK (principal_amount >= 0),
    interest_rate REAL NOT NULL CHECK (interest_rate >= 0),
    term_months INTEGER NOT NULL CHECK (term_months > 0),
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'PAID_OFF', 'DEFAULTED')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Investing: fixed assets. Use fixed_asset (no space) consistently.
CREATE TABLE IF NOT EXISTS fixed_asset (
    asset_id INTEGER PRIMARY KEY,
    asset_name TEXT NOT NULL,
    purchase_date DATE NOT NULL,
    purchase_price NUMERIC NOT NULL CHECK (purchase_price >= 0),
    useful_life_years INTEGER NOT NULL CHECK (useful_life_years > 0),
    salvage_value NUMERIC NOT NULL CHECK (salvage_value >= 0),
    depreciation_method TEXT NOT NULL
        CHECK (depreciation_method IN ('STRAIGHT_LINE', 'DECLINING_BALANCE')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (salvage_value <= purchase_price)
);

-- ============================================================
-- 3. CASHFLOW RECORDS AND BANK STATEMENT
-- ============================================================

-- Company's cashflow records.
CREATE TABLE IF NOT EXISTS ledger_cash_entry (
    entry_id INTEGER PRIMARY KEY,
    entry_date DATE NOT NULL,
    account_number INTEGER NOT NULL REFERENCES bank_account(account_number),
    amount NUMERIC NOT NULL CHECK (amount <> 0),
    category_id INTEGER NOT NULL REFERENCES cf_category(category_id),
    description TEXT,
    reference TEXT,
    invoice_id INTEGER REFERENCES sales_invoice(invoice_id),
    bill_id INTEGER REFERENCES supplier_bill(bill_id),
    loan_id INTEGER REFERENCES loan(loan_id),
    asset_id INTEGER REFERENCES fixed_asset(asset_id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ledger_cash_entry_date
    ON ledger_cash_entry(entry_date);
CREATE INDEX IF NOT EXISTS idx_ledger_cash_entry_ref
    ON ledger_cash_entry(reference);
CREATE INDEX IF NOT EXISTS idx_ledger_cash_entry_account
    ON ledger_cash_entry(account_number);

-- Bank statement lines imported from the bank.
CREATE TABLE IF NOT EXISTS bank_statement_line (
    line_id INTEGER PRIMARY KEY,
    account_number INTEGER NOT NULL REFERENCES bank_account(account_number),
    statement_date DATE NOT NULL,
    amount NUMERIC NOT NULL CHECK (amount <> 0),
    description TEXT,
    reference TEXT
);

CREATE INDEX IF NOT EXISTS idx_bank_statement_ref
    ON bank_statement_line(reference);
CREATE INDEX IF NOT EXISTS idx_bank_statement_date
    ON bank_statement_line(statement_date);
CREATE INDEX IF NOT EXISTS idx_bank_statement_account
    ON bank_statement_line(account_number);

-- ============================================================
-- 4. RECONCILIATION TABLES
-- ============================================================

-- One ledger entry can match at most one bank line, and vice versa.
CREATE TABLE IF NOT EXISTS recon_match (
    match_id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL UNIQUE REFERENCES ledger_cash_entry(entry_id),
    line_id INTEGER NOT NULL UNIQUE REFERENCES bank_statement_line(line_id),
    match_rule TEXT NOT NULL,
    matched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Supplier statement header.
CREATE TABLE IF NOT EXISTS supplier_statement (
    statement_id INTEGER PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES supplier(supplier_id),
    statement_date DATE NOT NULL,
    closing_balance NUMERIC NOT NULL
);

-- Supplier statement lines. BILL is used for supplier invoices.
CREATE TABLE IF NOT EXISTS supplier_statement_line (
    stmt_line_id INTEGER PRIMARY KEY,
    statement_id INTEGER NOT NULL REFERENCES supplier_statement(statement_id),
    bill_no TEXT NOT NULL,
    amount NUMERIC NOT NULL CHECK (amount <> 0),
    doc_type TEXT NOT NULL
        CHECK (doc_type IN ('BILL', 'CREDIT_NOTE', 'DEBIT_NOTE'))
);

-- Review flags generated by reconciliation checks.
CREATE TABLE IF NOT EXISTS recon_exception (
    exception_id INTEGER PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    entry_id INTEGER REFERENCES ledger_cash_entry(entry_id),
    line_id INTEGER REFERENCES bank_statement_line(line_id),
    bill_id INTEGER REFERENCES supplier_bill(bill_id),
    invoice_id INTEGER REFERENCES sales_invoice(invoice_id),
    stmt_line_id INTEGER REFERENCES supplier_statement_line(stmt_line_id),
    exception_type TEXT NOT NULL CHECK (
        exception_type IN (
            'MISSING_ENTRY',
            'MISSING_LINE',
            'AMOUNT_MISMATCH',
            'DUPLICATE_ENTRY',
            'DUPLICATE_LINE',
            'IN_BOOKS_NOT_BANK',
            'IN_BANK_NOT_BOOKS',
            'INVOICE_OVERPAID',
            'BILL_OVERPAID',
            'STMT_INVOICE_MISSING_IN_BOOKS',
            'STMT_AMOUNT_DIFFERS',
            'OTHER'
        )
    ),
    severity TEXT NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH')),
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED')),
    raised_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    detail TEXT,
    resolved_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_recon_exception_status
    ON recon_exception(status, severity);

-- ============================================================
-- 5. REPORTING VIEWS
-- ============================================================

DROP VIEW IF EXISTS v_cashflow_summary;
CREATE VIEW v_cashflow_summary AS
SELECT
    strftime('%Y-%m', e.entry_date) AS month,
    c.activity,
    ROUND(SUM(CASE WHEN e.amount > 0 THEN e.amount ELSE 0 END), 2) AS cash_in,
    ROUND(SUM(CASE WHEN e.amount < 0 THEN e.amount ELSE 0 END), 2) AS cash_out,
    ROUND(SUM(e.amount), 2) AS net_cash_flow
FROM ledger_cash_entry AS e
JOIN cf_category AS c ON c.category_id = e.category_id
GROUP BY strftime('%Y-%m', e.entry_date), c.activity;

DROP VIEW IF EXISTS v_cash_position;
CREATE VIEW v_cash_position AS
SELECT
    m.month,
    m.net_cash_flow,
    ROUND(
        (SELECT COALESCE(SUM(opening_balance), 0) FROM bank_account)
        + SUM(m.net_cash_flow) OVER (ORDER BY m.month),
        2
    ) AS closing_cash
FROM (
    SELECT month, SUM(net_cash_flow) AS net_cash_flow
    FROM v_cashflow_summary
    GROUP BY month
) AS m;

DROP VIEW IF EXISTS v_invoice_balance;
CREATE VIEW v_invoice_balance AS
SELECT
    i.invoice_id,
    i.invoice_no,
    cu.customer_name,
    i.due_date,
    i.total_amount,
    ROUND(COALESCE(SUM(e.amount), 0), 2) AS received,
    ROUND(i.total_amount - COALESCE(SUM(e.amount), 0), 2) AS outstanding
FROM sales_invoice AS i
JOIN customer AS cu ON cu.customer_id = i.customer_id
LEFT JOIN ledger_cash_entry AS e ON e.invoice_id = i.invoice_id
GROUP BY
    i.invoice_id, i.invoice_no, cu.customer_name, i.due_date, i.total_amount;

DROP VIEW IF EXISTS v_bill_balance;
CREATE VIEW v_bill_balance AS
SELECT
    b.bill_id,
    s.supplier_name,
    b.supplier_id,
    b.supplier_invoice_no,
    b.due_date,
    b.total_amount,
    ROUND(-COALESCE(SUM(e.amount), 0), 2) AS paid,
    ROUND(b.total_amount + COALESCE(SUM(e.amount), 0), 2) AS outstanding
FROM supplier_bill AS b
JOIN supplier AS s ON s.supplier_id = b.supplier_id
LEFT JOIN ledger_cash_entry AS e ON e.bill_id = b.bill_id
GROUP BY
    b.bill_id, s.supplier_name, b.supplier_id,
    b.supplier_invoice_no, b.due_date, b.total_amount;

DROP VIEW IF EXISTS v_unreconciled;
CREATE VIEW v_unreconciled AS
SELECT
    'BOOKS' AS side,
    e.entry_id AS id,
    e.entry_date AS txn_date,
    e.amount,
    e.reference,
    e.description
FROM ledger_cash_entry AS e
WHERE NOT EXISTS (
    SELECT 1 FROM recon_match AS rm WHERE rm.entry_id = e.entry_id
)
UNION ALL
SELECT
    'BANK' AS side,
    b.line_id AS id,
    b.statement_date AS txn_date,
    b.amount,
    b.reference,
    b.description
FROM bank_statement_line AS b
WHERE NOT EXISTS (
    SELECT 1 FROM recon_match AS rm WHERE rm.line_id = b.line_id
);

DROP VIEW IF EXISTS v_supplier_balance_check;
CREATE VIEW v_supplier_balance_check AS
SELECT
    s.supplier_name,
    st.statement_date,
    st.closing_balance AS supplier_says,
    ROUND(COALESCE((
        SELECT SUM(vb.outstanding)
        FROM v_bill_balance AS vb
        WHERE vb.supplier_id = st.supplier_id
    ), 0), 2) AS our_books_say,
    ROUND(
        st.closing_balance - COALESCE((
            SELECT SUM(vb.outstanding)
            FROM v_bill_balance AS vb
            WHERE vb.supplier_id = st.supplier_id
        ), 0),
        2
    ) AS variance
FROM supplier_statement AS st
JOIN supplier AS s ON s.supplier_id = st.supplier_id;