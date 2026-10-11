-- file · SQL
-- reconcile.sql : matching passes + exception checks (run after schema.sql and data are loaded)
 
PRAGMA foreign_keys = ON;
 
-- ============================================================
-- 6. RECONCILIATION ENGINE
-- ============================================================
-- The following checks operate on records already inserted into the tables.
-- They are safe to rerun because matches are unique and exceptions use dedupe_key.
 
-- Pass 1: same account + same non-empty reference + same amount.
WITH candidates AS (
    SELECT e.entry_id, b.line_id
    FROM ledger_cash_entry AS e
    JOIN bank_statement_line AS b
      ON b.account_number = e.account_number
     AND e.reference IS NOT NULL
     AND TRIM(e.reference) <> ''
     AND b.reference = e.reference
     AND ROUND(b.amount, 2) = ROUND(e.amount, 2)
    WHERE NOT EXISTS (
        SELECT 1 FROM recon_match AS rm WHERE rm.entry_id = e.entry_id
    )
      AND NOT EXISTS (
        SELECT 1 FROM recon_match AS rm WHERE rm.line_id = b.line_id
    )
),
entry_pick AS (
    SELECT entry_id, MIN(line_id) AS line_id
    FROM candidates
    GROUP BY entry_id
),
line_pick AS (
    SELECT MIN(entry_id) AS entry_id, line_id
    FROM entry_pick
    GROUP BY line_id
)
INSERT OR IGNORE INTO recon_match (entry_id, line_id, match_rule)
SELECT entry_id, line_id, 'REF_AMOUNT'
FROM line_pick;
 
-- Pass 2: same account + same amount + dates within 3 days.
WITH candidates AS (
    SELECT e.entry_id, b.line_id
    FROM ledger_cash_entry AS e
    JOIN bank_statement_line AS b
      ON b.account_number = e.account_number
     AND ROUND(b.amount, 2) = ROUND(e.amount, 2)
     AND ABS(julianday(b.statement_date) - julianday(e.entry_date)) <= 3
    WHERE NOT EXISTS (
        SELECT 1 FROM recon_match AS rm WHERE rm.entry_id = e.entry_id
    )
      AND NOT EXISTS (
        SELECT 1 FROM recon_match AS rm WHERE rm.line_id = b.line_id
    )
),
entry_pick AS (
    SELECT entry_id, MIN(line_id) AS line_id
    FROM candidates
    GROUP BY entry_id
),
line_pick AS (
    SELECT MIN(entry_id) AS entry_id, line_id
    FROM entry_pick
    GROUP BY line_id
)
INSERT OR IGNORE INTO recon_match (entry_id, line_id, match_rule)
SELECT entry_id, line_id, 'AMOUNT_DATE'
FROM line_pick;
 
-- Duplicate ledger entries: same account, reference and amount.
INSERT INTO recon_exception (
    dedupe_key, exception_type, severity, entry_id, detail
)
SELECT
    'DUP:' || e.entry_id,
    'DUPLICATE_ENTRY',
    'HIGH',
    e.entry_id,
    'Entry ' || e.entry_id || ' duplicates entry ' || first.entry_id
        || ' (ref ' || e.reference || ', amount ' || e.amount || ')'
FROM ledger_cash_entry AS e
JOIN ledger_cash_entry AS first
  ON first.account_number = e.account_number
 AND first.reference = e.reference
 AND first.amount = e.amount
 AND first.entry_id < e.entry_id
WHERE e.reference IS NOT NULL
  AND TRIM(e.reference) <> ''
  AND first.entry_id = (
      SELECT MIN(x.entry_id)
      FROM ledger_cash_entry AS x
      WHERE x.account_number = e.account_number
        AND x.reference = e.reference
        AND x.amount = e.amount
  )
ON CONFLICT (dedupe_key) DO NOTHING;
 
-- Unmatched ledger and bank records with the same reference/account but different amount.
INSERT INTO recon_exception (
    dedupe_key, exception_type, severity, entry_id, line_id, detail
)
SELECT
    'AMT:' || e.entry_id || ':' || b.line_id,
    'AMOUNT_MISMATCH',
    'HIGH',
    e.entry_id,
    b.line_id,
    'Ref ' || COALESCE(e.reference, '') || ': books ' || e.amount
        || ' vs bank ' || b.amount
        || ' (difference ' || ROUND(b.amount - e.amount, 2) || ')'
FROM ledger_cash_entry AS e
JOIN bank_statement_line AS b
  ON b.account_number = e.account_number
 AND b.reference = e.reference
WHERE NOT EXISTS (
    SELECT 1 FROM recon_match AS rm WHERE rm.entry_id = e.entry_id
)
  AND NOT EXISTS (
    SELECT 1 FROM recon_match AS rm WHERE rm.line_id = b.line_id
)
  AND ROUND(b.amount, 2) <> ROUND(e.amount, 2)
ON CONFLICT (dedupe_key) DO NOTHING;
 
-- Book entries not found on the bank statement.
INSERT INTO recon_exception (
    dedupe_key, exception_type, severity, entry_id, detail
)
SELECT
    'NOBANK:' || e.entry_id,
    'IN_BOOKS_NOT_BANK',
    CASE
        WHEN julianday('now') - julianday(e.entry_date) > 14 THEN 'HIGH'
        ELSE 'MEDIUM'
    END,
    e.entry_id,
    'Books entry ' || e.entry_id || ' ('
        || COALESCE(e.reference, 'no reference') || ', ' || e.amount
        || ') has no matching bank line'
FROM ledger_cash_entry AS e
WHERE NOT EXISTS (
    SELECT 1 FROM recon_match AS rm WHERE rm.entry_id = e.entry_id
)
  AND NOT EXISTS (
    SELECT 1 FROM recon_exception AS x
    WHERE x.dedupe_key = 'NOBANK:' || e.entry_id
)
ON CONFLICT (dedupe_key) DO NOTHING;
 
-- Bank lines not found in the books.
INSERT INTO recon_exception (
    dedupe_key, exception_type, severity, line_id, detail
)
SELECT
    'NOBOOK:' || b.line_id,
    'IN_BANK_NOT_BOOKS',
    'MEDIUM',
    b.line_id,
    'Bank line ' || b.line_id || ' ('
        || COALESCE(b.description, '') || ', ' || b.amount
        || ') is not recorded in the books'
FROM bank_statement_line AS b
WHERE NOT EXISTS (
    SELECT 1 FROM recon_match AS rm WHERE rm.line_id = b.line_id
)
  AND NOT EXISTS (
    SELECT 1 FROM recon_exception AS x
    WHERE x.dedupe_key = 'NOBOOK:' || b.line_id
)
ON CONFLICT (dedupe_key) DO NOTHING;
 
-- Customer overpayments.
INSERT INTO recon_exception (
    dedupe_key, exception_type, severity, invoice_id, detail
)
SELECT
    'OVERRCV:' || invoice_id,
    'INVOICE_OVERPAID',
    'MEDIUM',
    invoice_id,
    'Invoice ' || invoice_no || ' total ' || total_amount
        || ' but received ' || received
FROM v_invoice_balance
WHERE outstanding < 0
ON CONFLICT (dedupe_key) DO NOTHING;
 
-- Supplier bill overpayments.
INSERT INTO recon_exception (
    dedupe_key, exception_type, severity, bill_id, detail
)
SELECT
    'OVERPAY:' || bill_id,
    'BILL_OVERPAID',
    'HIGH',
    bill_id,
    'Bill ' || supplier_invoice_no || ' (' || supplier_name
        || ') total ' || total_amount || ' but paid ' || paid
FROM v_bill_balance
WHERE outstanding < 0
ON CONFLICT (dedupe_key) DO NOTHING;
 
-- Supplier statement bills missing from our records or with different amounts.
INSERT INTO recon_exception (
    dedupe_key, exception_type, severity, stmt_line_id, bill_id, detail
)
SELECT
    'STMT:' || sl.stmt_line_id,
    CASE
        WHEN b.bill_id IS NULL THEN 'STMT_INVOICE_MISSING_IN_BOOKS'
        ELSE 'STMT_AMOUNT_DIFFERS'
    END,
    'HIGH',
    sl.stmt_line_id,
    b.bill_id,
    CASE
        WHEN b.bill_id IS NULL THEN
            s.supplier_name || ' bill ' || sl.bill_no || ' (' || sl.amount
                || ') is missing from our books'
        ELSE
            s.supplier_name || ' bill ' || sl.bill_no || ': statement '
                || sl.amount || ' vs our bill ' || b.total_amount
    END
FROM supplier_statement_line AS sl
JOIN supplier_statement AS st ON st.statement_id = sl.statement_id
JOIN supplier AS s ON s.supplier_id = st.supplier_id
LEFT JOIN supplier_bill AS b
  ON b.supplier_id = st.supplier_id
 AND b.supplier_invoice_no = sl.bill_no
WHERE sl.doc_type = 'BILL'
  AND (
      b.bill_id IS NULL
      OR ROUND(b.total_amount, 2) <> ROUND(sl.amount, 2)
  )
ON CONFLICT (dedupe_key) DO NOTHING;