--Seed data · SQL
-- =====================================================================
-- seed_data.sql : sample SME data (Aug-Sep 2026) with deliberately planted errors
-- Run after schema.sql, before reconcile.sql. Replace with your own data when ready.
-- =====================================================================
 
PRAGMA foreign_keys = ON;
 
INSERT INTO bank_account (account_number, account_name, bank_name, currency, opening_balance) VALUES
 (1001, 'Operating Account', 'DBS', 'SGD', 10000);
 
INSERT INTO cf_category (category_id, category_name, activity, direction) VALUES
 (1,  'Customer receipts',       'OPERATING', 'IN'),
 (2,  'Supplier payments',       'OPERATING', 'OUT'),
 (3,  'Payroll',                 'OPERATING', 'OUT'),
 (4,  'Rent & utilities',        'OPERATING', 'OUT'),
 (5,  'Taxes paid',              'OPERATING', 'OUT'),
 (6,  'Bank fees & interest',    'OPERATING', 'OUT'),
 (7,  'Equipment purchase',      'INVESTING', 'OUT'),
 (8,  'Asset disposal proceeds', 'INVESTING', 'IN'),
 (9,  'Loan drawdown',           'FINANCING', 'IN'),
 (10, 'Loan repayment',          'FINANCING', 'OUT'),
 (11, 'Share issuance',          'FINANCING', 'IN'),
 (12, 'Dividends paid',          'FINANCING', 'OUT');
 
INSERT INTO customer (customer_id, customer_name, payment_terms_days) VALUES
 (1, 'Orchid Retail', 30), (2, 'Lion Logistics', 30), (3, 'Merlion Cafe Group', 30);
 
INSERT INTO supplier (supplier_id, supplier_name, payment_terms_days) VALUES
 (1, 'Alpha Packaging', 30), (2, 'BrightPrint', 30), (3, 'CloudHost', 30);
 
INSERT INTO sales_invoice (invoice_id, invoice_no, customer_id, invoice_date, due_date, total_amount, status) VALUES
 (1, 'S-1001', 1, '2026-08-05', '2026-09-04', 5000, 'PAID'),
 (2, 'S-1002', 2, '2026-08-12', '2026-09-11', 3200, 'PAID'),
 (3, 'S-1003', 3, '2026-08-20', '2026-09-19', 1800, 'PAID'),
 (4, 'S-1004', 1, '2026-09-02', '2026-10-02', 4500, 'PAID');
 
INSERT INTO supplier_bill (bill_id, bill_no, supplier_id, supplier_invoice_no, bill_date, due_date, total_amount, status) VALUES
 (1, 'BILL-001', 1, 'INV-A77', '2026-08-10', '2026-09-09', 2400, 'PAID'),
 (2, 'BILL-002', 2, 'BP-310',  '2026-08-18', '2026-09-17', 1250, 'PAID'),   -- keyed 1,250; supplier says 1,520
 (3, 'BILL-003', 3, 'CH-0912', '2026-09-01', '2026-10-01',  600, 'PAID'),
 (4, 'BILL-004', 1, 'INV-A81', '2026-09-05', '2026-10-05', 3100, 'PENDING');
 
INSERT INTO loan (loan_id, loan_no, lender_name, loan_date, principal_amount, interest_rate, term_months, status) VALUES
 (1, 'LN-001', 'DBS SME Loan', '2026-08-02', 15000, 0.055, 36, 'ACTIVE');
 
INSERT INTO fixed_asset (asset_id, asset_name, purchase_date, purchase_price, useful_life_years, salvage_value, depreciation_method) VALUES
 (1, 'Packing machine', '2026-08-03', 8000, 5, 500, 'STRAIGHT_LINE');
 
-- Books
INSERT INTO ledger_cash_entry (entry_id, entry_date, account_number, amount, category_id, description, reference, invoice_id, bill_id, loan_id, asset_id) VALUES
 (1,  '2026-08-01', 1001,  20000, 11, 'Share capital injection', 'CAP-001',   NULL, NULL, NULL, NULL),
 (2,  '2026-08-02', 1001,  15000,  9, 'Loan drawdown',           'LN-001',    NULL, NULL, 1,    NULL),
 (3,  '2026-08-03', 1001,  -8000,  7, 'Packing machine',         'PO-EQ1',    NULL, NULL, NULL, 1),
 (4,  '2026-09-03', 1001,   5000,  1, 'Receipt S-1001',          'S-1001',    1,    NULL, NULL, NULL),
 (5,  '2026-09-10', 1001,   3200,  1, 'Receipt S-1002',          'S-1002',    2,    NULL, NULL, NULL),
 (6,  '2026-09-18', 1001,   1800,  1, 'Receipt S-1003',          'S-1003',    3,    NULL, NULL, NULL),
 (7,  '2026-09-12', 1001,  -2400,  2, 'Pay Alpha INV-A77',       'INV-A77',   NULL, 1,    NULL, NULL),
 (8,  '2026-09-12', 1001,  -2400,  2, 'Pay Alpha INV-A77',       'INV-A77',   NULL, 1,    NULL, NULL),  -- DUPLICATE entry
 (9,  '2026-09-20', 1001,  -1250,  2, 'Pay BrightPrint BP-310',  'BP-310',    NULL, 2,    NULL, NULL),
 (10, '2026-09-25', 1001,  -9000,  3, 'Payroll Sep',             'PAY-0925',  NULL, NULL, NULL, NULL),
 (11, '2026-09-01', 1001,  -2500,  4, 'Rent Sep',                'RENT-SEP',  NULL, NULL, NULL, NULL),
 (12, '2026-09-28', 1001,  -1000, 10, 'Loan repayment 1',        'LN-001-R1', NULL, NULL, 1,    NULL),
 (13, '2026-09-29', 1001,   -600,  2, 'Pay CloudHost CH-0912',   'CH-0912',   NULL, 3,    NULL, NULL),  -- no bank line
 (14, '2026-09-30', 1001,  -2000, 12, 'Q3 dividend',             'DIV-Q3',    NULL, NULL, NULL, NULL),
 (15, '2026-09-28', 1001,   5400,  1, 'Receipt S-1004',          'S-1004',    4,    NULL, NULL, NULL);  -- exceeds invoice 4,500
 
-- Bank
INSERT INTO bank_statement_line (line_id, account_number, statement_date, amount, description, reference) VALUES
 (1,  1001, '2026-08-01',  20000, 'CAPITAL TRANSFER CAP-001', 'CAP-001'),
 (2,  1001, '2026-08-02',  15000, 'LOAN DISBURSEMENT LN-001', 'LN-001'),
 (3,  1001, '2026-08-03',  -8000, 'PAYMENT PO-EQ1',           'PO-EQ1'),
 (4,  1001, '2026-09-04',   5000, 'FAST S-1001 ORCHID',       'S-1001'),
 (5,  1001, '2026-09-10',   3200, 'FAST S-1002 LION',         'S-1002'),
 (6,  1001, '2026-09-19',   1800, 'FAST S-1003 MERLION',      'S-1003'),
 (7,  1001, '2026-09-13',  -2400, 'GIRO ALPHA INV-A77',       'INV-A77'),   -- paid once
 (8,  1001, '2026-09-21',  -1520, 'GIRO BRIGHTPRINT BP-310',  'BP-310'),    -- amount differs
 (9,  1001, '2026-09-25',  -9000, 'GIRO PAYROLL',             'PAY-0925'),
 (10, 1001, '2026-09-02',  -2500, 'GIRO LANDLORD',            NULL),        -- no reference
 (11, 1001, '2026-09-28',  -1000, 'LOAN INSTALMENT',          'LN-001-R1'),
 (12, 1001, '2026-09-30',  -2000, 'DIVIDEND PAYOUT',          'DIV-Q3'),
 (13, 1001, '2026-09-29',   5400, 'FAST S-1004 ORCHID',       'S-1004'),
 (14, 1001, '2026-09-30',    -35, 'MONTHLY ACCOUNT FEE',      NULL);        -- not in books
 
-- Supplier statements (doc_type BILL = supplier invoice; this schema has no PAYMENT line type)
INSERT INTO supplier_statement (statement_id, supplier_id, statement_date, closing_balance) VALUES
 (1, 1, '2026-09-30', 4050),   -- Alpha: INV-A81 3,100 + INV-A90 950
 (2, 2, '2026-09-30',    0);   -- BrightPrint: BP-310 paid in full
 
INSERT INTO supplier_statement_line (stmt_line_id, statement_id, bill_no, amount, doc_type) VALUES
 (1, 1, 'INV-A81', 3100, 'BILL'),
 (2, 1, 'INV-A90',  950, 'BILL'),   -- not in our bills
 (3, 2, 'BP-310',  1520, 'BILL');   -- our bill says 1,250