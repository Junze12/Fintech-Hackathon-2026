
-- review_queries.sql : example queries to inspect results. Run individually.
 
-- ============================================================
-- 7. EXAMPLE REVIEW QUERIES
-- ============================================================
-- Uncomment and run these queries separately when you want to inspect results.
--
-- Cashflow summary by month and activity:
-- SELECT * FROM v_cashflow_summary ORDER BY month, activity;
--
-- Open exceptions, highest severity first:
-- SELECT exception_id, exception_type, severity, detail
-- FROM recon_exception
-- WHERE status = 'OPEN'
-- ORDER BY CASE severity
--     WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3
-- END, exception_id;
--
-- Unreconciled book and bank transactions:
-- SELECT * FROM v_unreconciled ORDER BY txn_date;
--
-- Supplier statement vs our payables:
-- SELECT * FROM v_supplier_balance_check;
--
-- Overdue receivables:
-- SELECT * FROM v_invoice_balance
-- WHERE outstanding > 0 AND due_date < DATE('now');
 