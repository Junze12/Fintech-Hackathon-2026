# Permission tiers

Feeds the security self-assessment report (deliverable #5). Keep in sync with
`src/copilot/policy/roles.py` (`TIERS`) and the tools' `min_role`.

## Tiers

Each tier can do everything the tiers above it in this table can do.

| Tier | Can do | Built so far |
|---|---|---|
| Viewer | Read-only: analysis, forecasts, alerts, financing comparisons | get_metrics, get_ageing, get_cash_trend, get_health_ratios, get_financial_statements, compare_periods, get_expense_breakdown, get_cash_position, forecast_balance, get_alerts, get_obligations, get_cash_summary, run_what_if, recommend_actions, find_financing, list_applications, list_payees, list_bills, list_invoices, list_receipts, list_reminders, list_adjustments |
| Staff | Viewer + draft reminders, set personal alert rules, pre-fill applications, draft adjustments | draft_reminder, set_cash_floor, prefill_application, draft_adjustment |
| Owner | Staff + send reminders, schedule payments, submit financing applications, mark invoices paid, apply and undo adjustments, save and remove forecast assumptions | schedule_payment, submit_application, send_reminder, mark_invoice_paid, apply_adjustment, undo_adjustment, save_assumption, remove_assumption |

## How tiers are enforced

1. **The role comes from the session.** The UI builds an `Actor(user_id, role, business_id,
   session_id)` when the user signs in. Nothing the user or the LLM types can change it. A
   `role` argument in a tool call is rejected as an unknown field.
2. **The LLM is only offered allowed tools.** `Gateway.specs(actor)` lists only tools at or
   below the actor's tier.
3. **The role is re-checked on every call**, in case the LLM names a tool it wasn't offered.
   The result is `denied`, and the attempt is audited.
4. **The role is re-checked at confirmation.** If the user's role changed between the request
   and the confirmation, the action is denied.
5. **Owner money movements need confirmation:** `schedule_payment` runs only after the user's
   next message is `confirm <code>`. The guards (allowlist, verification, limits, bill checks)
   run when the payment is requested and again when it is confirmed.

6. **Personal settings stay personal.** `set_cash_floor` saves a floor for the signed-in
   user only (keyed by business and user id from the session). Other users keep their own
   floor or the default.
7. **The demo clock is not a tier action.** Any signed-in user can advance the simulated
   clock from the sidebar (not an LLM tool). It only runs payments the owner already
   confirmed, and the guards are re-checked before each one runs (R8).
8. **Submitting a financing application is owner-only and confirmed** like a payment.
   Eligibility is re-checked at request and at confirmation. Staff can only save drafts.
9. **Sending a reminder is owner-only and confirmed** (4d). Staff draft, the owner sends. The
   tool has no recipient argument: a reminder goes only to the invoice's own customer. At most
   one per invoice per 7 simulated days.
10. **Marking an invoice paid is owner-only and confirmed** (4d). It only links a receipt that
    is already in the bank (same customer, not used before, no more than outstanding), so it
    can't create cash or hide a receivable.
11. **Anything with an external effect needs confirmation, by construction.** Tools that move
    money, change the books or reach someone outside the business declare
    `external_effect=True`; the registry refuses to register one without
    `needs_confirmation=True`. All of them are owner-only.
12. **This table is checked by a test.** `roles.CAPABILITY_TOOLS` maps each tier capability to
    its tools; `test_registry.py` checks every tool's `min_role` against it and parses the
    table above against the registry (it caught 4a's two read tools missing from this file).
13. **Book edits: staff draft, the owner applies (chunk 13).** `draft_adjustment` saves a draft
    that counts in no figure; `apply_adjustment` / `undo_adjustment` are owner-only and
    confirmed, with the exact effect on that month's net profit restated in code. Only the last
    3 complete months are open. Adjustments never move money or overwrite imported data.
14. **Saved forecast assumptions are owner-only and confirmed (chunk 13)**, because they change
    everyone's forecast, alerts and financing need. Staff and viewers use `run_what_if`, which
    saves nothing.
15. **The API (chunk 9) changes nothing here.** It signs in with the same demo picker, keeps the role in the server-side session and calls the same gateway; a `role` field in a request body is rejected (`tests/unit/test_api.py`).

## Tests

- `tests/unit/test_registry.py`: the tools each role is shown; Viewer and Staff denied
  `schedule_payment`; Viewer denied `draft_reminder` while Staff is allowed; smuggled `role`,
  `business_id` and `confirmed` arguments rejected; every attempt audited.
- `tests/unit/test_confirmations.py`: the role is re-checked at confirmation; a pending action
  can't be confirmed from another session or by another user.
- `tests/unit/test_guards.py`: every payment guard, including the limit boundaries, the
  floor guard, and the execution-time re-check.
- `tests/unit/test_registry.py`: `set_cash_floor` denied for Viewer, saved for Staff,
  personal to that user, and blocked above S$10m.
- `tests/unit/test_scheduler.py`: the clock isn't an LLM tool; a payment whose payee
  changed after confirmation is blocked when it comes due.
- `tests/unit/test_owner_actions.py` (4d): staff drafts, owner sends with the code; no
  recipient argument; one reminder per week; mark paid moves no money, rejects another
  customer's receipt, money out, a used or settled receipt, a receipt dated before the
  invoice, and more than outstanding.
- `tests/redteam/` (4d): privilege-escalation cases RT-PE-01 to RT-PE-05 (viewer claims to be
  owner, smuggled role and business, staff tries every owner action, hidden clock, injected
  "admin mode").
- `tests/unit/test_applications.py`: Viewer can't pre-fill; Staff pre-fills but can't submit;
  Owner submits only with the code; an ineligible product is blocked; eligibility is re-checked
  at submission; another business can't submit the draft; the database refuses "approved".
