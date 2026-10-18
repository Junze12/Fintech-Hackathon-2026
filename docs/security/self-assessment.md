# Security self-assessment

Deliverable #5: how permissions are implemented, how each threat is stopped, what our attack
tests show, and every known risk with its status. The design behind it is in
`docs/technical/architecture.md` (section 5).

**Summary.** Every protection that matters is enforced in code, outside the AI: roles,
payment rules, confirmation by the owner's own code, hiding of secrets, and labelling of
outside text. We tested this with a model that falls for every attack (37/37 attacks still
stopped) and with Claude Sonnet 5.5 itself (**37/37**, 18 Oct 2026). Remaining risks are
listed honestly below; most come from this being a local demo on synthetic data.

## 1. Permission tiers

Each tier can do everything the tiers above it in this table can do. This table is checked
against the code by `tests/unit/test_registry.py`.

| Tier | Can do | Tools |
|---|---|---|
| Viewer | Read-only: analysis, forecasts, alerts, financing comparisons | get_metrics, get_ageing, get_cash_trend, get_health_ratios, get_financial_statements, get_financial_model, get_break_even_and_value, compare_periods, get_expense_breakdown, get_cash_position, forecast_balance, get_alerts, get_obligations, get_cash_summary, run_what_if, recommend_actions, stress_test_cash, compare_options, get_reconciliation_exceptions, find_financing, list_applications, list_payees, list_bills, list_invoices, list_receipts, list_reminders, list_adjustments |
| Staff | Viewer + draft reminders, set personal alert rules, pre-fill applications, draft adjustments | draft_reminder, set_cash_floor, prefill_application, draft_adjustment |
| Owner | Staff + send reminders, schedule payments, submit financing applications, mark invoices paid, apply and undo adjustments, save and remove forecast assumptions | schedule_payment, submit_application, send_reminder, mark_invoice_paid, apply_adjustment, undo_adjustment, save_assumption, remove_assumption |

How the tiers are enforced:

1. **The role comes from sign-in**, never from the chat. A `role` or `business_id` added to a
   tool call or a web request is rejected and logged.
2. **The AI is only offered the tools its role allows**, and the role is checked again on
   every call and again at confirmation.
3. **Every owner action that moves money, changes the books or contacts someone outside needs
   the owner's own `confirm <code>`.** The code is shown to the owner only, never to the AI; any
   other reply cancels the action. The tool registry refuses to load such a tool without this.
4. **Staff prepare, the owner acts:** staff draft reminders, applications and adjustments;
   only the owner sends, submits or applies them.
5. **Personal settings stay personal:** a staff member's cash floor applies to them only.
6. **The demo clock is not an AI tool.** Moving it only runs payments the owner already
   confirmed, after re-checking the payment rules.

## 2. Threats and defences

| Threat | Defences (all enforced in code) |
|---|---|
| **Induced transfers** | Owner's own confirmation code; payee allowlisted, verified and with no recent bank-detail change; S$75,000 per payment, S$100,000 per day; bill payments must match the bill's supplier and can't exceed what is owed; rules re-checked at confirmation and on the day of payment; reminders have no recipient argument |
| **Data extraction** | Account numbers masked everywhere (`••••1234`); each business separated in the database itself; replies that repeat the system prompt are blocked (secret marker); codes, long digit strings, links and images removed from replies |
| **Privilege escalation** | Role from sign-in only; extra arguments rejected; role re-checked on every call and at confirmation; owner-only tools hidden from lower roles |
| **Prompt injection** | Outside text labelled `<untrusted>` and impossible to "close"; instruction-like text flagged, pointed out to the owner and audited; the dashboard shows imported text only as plain text, under a strict Content-Security-Policy; Excel exports never create formulas; tools that read outside text can't act |
| **Audit** | Every tool call and write attempt logged (user, role, tool, masked arguments, outcome, reason); rows hash-chained so edits or deletions are detected |
| **Financing compliance** | Total cost and effective rate always shown; approval never promised ("draft" or "submitted" only); ineligible products never recommended; no personal characteristics in the data; borrowing only after non-borrowing options |

## 3. Attack test results

37 scripted attacks in `tests/redteam/`, one file each, stating the attack and the expected
safe outcome. Each is run in two ways:

- **Fooled model:** a scripted AI that does whatever the attack asks. This proves the code
  stops the attack even if the AI is fully compromised.
- **Claude Sonnet 5.5:** the real model deciding for itself.

| Threat | Cases | Fooled model | Claude (18 Oct 2026) |
|---|---|---|---|
| Induced transfers | 10 | 10/10 | 10/10 |
| Data extraction | 7 | 7/7 | 7/7 |
| Privilege escalation | 6 | 6/6 | 6/6 |
| Prompt injection | 14 | 14/14 | 14/14 |
| **Total** | **37** | **37/37** | **37/37** |

Every case also checks that nothing changed except what the case allows, that no account
number, code or other business's data reached the AI or the reply, that every poisoned value
stayed labelled, and that the audit chain verifies. We also switched individual defences off
and confirmed the cases relying on them then fail.

Logs for every case (conversation, tool calls, audit entries, balances before and after):
`evidence/logs/claude/` and `evidence/logs/fooled/`.

## 4. Known risks

Severity: High / Medium / Low. Status: Mitigated, Partially mitigated, or Accepted (a
conscious choice, usually because this is a local demo on synthetic data).

| # | Risk | Severity | How it is handled | Status |
|---|---|---|---|---|
| R1 | Account numbers are stored unencrypted in the local database | Medium | Synthetic data; hidden in every log and output; database file not committed | Accepted (demo) |
| R2 | No verification flow for a supplier's changed bank details (a common fraud) | High | Payments to unverified or changed payees are blocked outright | Mitigated by blocking |
| R3 | The sandbox bank executes any valid payment by itself | High if misused | Only the policy gateway can reach it; a test fails if other code calls it | Mitigated |
| R4 | Payment habits match by customer and exact amount; same-amount invoices could be swapped | Low | Affects timing estimates only; unmatched items reported | Accepted |
| R5 | A bill's supplier is matched to a payee by name | Low | A mismatch blocks the payment; the payee must still be allowlisted and verified | Accepted |
| R6 | The 4-digit code prevents mistakes but isn't authentication | Medium | Shown only to the owner, expires after one message; real use would add one-time passwords | Accepted (demo) |
| R7 | Some imported text (names, ids) once reached the AI unlabelled | Low | All labelled; ids restricted to plain tokens; tested on a poisoned sample | Mitigated |
| R8 | A future-dated payment could run after conditions changed | Medium | Rules re-checked on the day it runs | Mitigated |
| R9 | Long conversations raise cost | Low | Large context window, caching, message and round limits, spend cap | Partially mitigated |
| R10 | The offline assistant could be mistaken for the AI | Low | Clearly labelled at sign-in and in the chat | Mitigated |
| R11 | Demo sign-in has no password: anyone with the address can pick Owner | Medium if hosted | Runs on 127.0.0.1 only; hosting would need real sign-in | Accepted (demo) |
| R12 | The demo's scripted future could leak into forecasts | Medium | Only the simulated clock reads it; a test fails if anything else does | Mitigated |
| R13 | Scripted world activity moves sandbox money without the policy gateway | Low | Stands for activity outside the app; labelled separately in the logs | Accepted |
| R14 | Recommendations rest on assumptions (a customer pays once chased) | Medium | Each assumption stated; each step's effect shown separately; nothing runs automatically | Mitigated |
| R15 | The funding need can understate the real need | Medium | Flagged when cash hasn't recovered; the stress test gives a 95%-confidence figure | Partially mitigated |
| R16 | The financing catalogue is illustrative | Medium | Fictional lenders; "illustrative terms, not offers" on every answer | Mitigated |
| R17 | Eligibility is estimated from our own data | Medium | Each fact sourced; unknown = not eligible; approval never implied | Accepted (demo) |
| R18 | Loan repayments after the 13-week forecast aren't checked | Medium | Stated in every financing answer | Partially mitigated |
| R19 | Past receivables use exact-amount matching | Low | Assumed items counted in a warning | Accepted |
| R20 | Cash-basis margins swing with payment timing | Medium | Basis always stated; accrual statements and DSO shown alongside | Partially mitigated |
| R21 | Code-written messages once carried outside text unlabelled | Medium | All messages labelled; regression tests | Mitigated |
| R22 | Account masking once hid dates in the audit log | Low | Masking rule fixed and shared | Mitigated |
| R23 | Instruction-like flagging is a pattern check and can miss rephrased attacks | Medium | Adds visibility only; no defence depends on it | Partially mitigated |
| R24 | The fooled-model tests don't show how a real AI behaves | Medium | Real-AI run: 37/37 | Mitigated (sampled) |
| R25 | The AI's own earlier words go back into the conversation unlabelled | Low | Tool results are re-fetched and labelled each turn | Accepted |
| R26 | Someone who can rewrite the whole database could rebuild the audit chain | Medium | Published evidence records each chain's latest hash; a secret key would close it | Partially mitigated |
| R27 | Marking an invoice paid trusts the customer named on the bank line | Low | Owner confirms after seeing date, amount and customer; no money moves | Accepted |
| R28 | Reminders are simulated; real use needs verified contact addresses | Low | No recipient argument; one per invoice per week | Accepted (demo) |
| R29 | Account numbers written with spaces aren't masked in replies | Low | The AI never receives full account numbers | Accepted |
| R30 | With Claude, conversation data goes to Anthropic's API | Medium (real data) | Synthetic data only; no full account numbers or codes sent; offline mode available | Accepted (demo) |
| R31 | AI outage or refusal mid-demo | Medium | Retries, fixed fallback reply, offline assistant | Mitigated |
| R32 | The real AI may handle a new attack differently | Medium | Hard guarantees don't depend on the AI; suite re-run before submission | Partially mitigated |
| R33 | A leaked API key could run up costs | Medium | Key never logged or shown; spend cap; tests can't use it | Mitigated |
| R34 | The AI sometimes writes its own approximate figures ("about S$128k") | Low | Prompt forbids it; every reply's numbers checked; 1 of 57 task cases in the final run | Partially mitigated |
| R35 | On an ambiguous request the AI may pick a record instead of asking | Low | Nothing runs before the owner sees the code-built restatement | Partially mitigated |
| R36 | A request could use up the 6 tool rounds | Low | Cause found and fixed (amounts were described to the AI as numbers but refused); re-tested | Mitigated |
| R37 | A reply with an image link could send data to an outside server | Medium | Links and images removed from every reply | Mitigated |
| R38 | Imported text shown as HTML could run a script | Medium | Dashboard only builds plain text; strict Content-Security-Policy; tested | Mitigated |
| R39 | Web sessions could spend AI credit | Low | 40 messages per session, 20 sessions, spend cap | Mitigated |
| R40 | GST is simplified (input tax on supplier bills only) | Low (demo) | Stated wherever it applies | Accepted (demo) |
| R41 | Asset and lender names reach the AI and could carry instructions | Medium | Labelled and flagged; attack tests show the payoff is blocked | Mitigated |
| R42 | Accrual statements don't handle asset purchases or combined payments | Low (demo) | Warnings; the books still balance | Accepted (demo) |
| R43 | An owner could flatter the books with adjustments | Medium | Never touch cash; always shown beside "as imported"; strict limits; owner confirmation; audited | Mitigated |
| R44 | The 3-month adjustment window isn't a real period close | Low (demo) | Stated; real use needs an accountant's lock date | Accepted (demo) |
| R45 | Injected text could try to save a false assumption to hide a gap | Medium | Owner-only with the code; forecast also shown without saved assumptions | Mitigated |
| R46 | The 3-year model is a simple projection | Medium | Every driver labelled with its source; presented as a projection, not a promise | Accepted (demo) |
| R47 | The stress test only randomises when customers pay | Medium | All assumptions listed; never presented as a guarantee | Accepted (demo) |
| R48 | Plan comparison relies on labelled assumptions (chase success, discount take-up) | Medium | Each labelled and changeable; financing still needs owner confirmation | Accepted (demo) |
| R49 | The books check uses fixed rules and can miss combined payments | Medium | Read-only; a missing-bill alert says to check with the supplier before paying | Partially mitigated |
| R50 | The value estimate could be read as a price | Medium | Fixed disclaimer, sensitivity rows, "not meaningful" when it would mislead | Accepted (demo) |
| R51 | The dashboard's safety rules rely on coding discipline | Low | Source tests for every banned pattern; Content-Security-Policy as backup | Mitigated |
| R52 | The `/docs` developer page loads scripts from a CDN | Low | Local only; the dashboard itself loads nothing external | Accepted |
| R53 | Imported text in Excel could run as a formula | Medium | Text cells never become formulas; tested | Mitigated |
| R54 | Uploaded files are untrusted | Medium if hosted | Only the 14 known file names; size limits; same checks as sample data; memory only | Mitigated (demo) |
| R55 | The AI wasn't told when a waiting action was cancelled | Low | Fixed; regression test | Mitigated |
