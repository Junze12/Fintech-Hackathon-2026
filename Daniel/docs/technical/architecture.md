# Architecture

Six layers plus a UI. Each layer calls only the layers below it.

```
ui/            Streamlit app — calls agent.handle(message, session) only
agent/         LLM loop, prompts, conversation state; LLM provider behind agent/llm.py
policy/        guards every write action: roles, limits, confirmation, audit log
tools/         thin wrappers exposing domain functions to the LLM
domain         analysis/, cashflow/, financing/, categorize.py — pure, deterministic, no LLM
store.py       SQLite repository, every query scoped by business_id
sandbox/       simulated accounts, ledger and clock in the same SQLite DB
adapters/      external formats (CSV) → models in schemas.py
```

## Data flow (chunk 1)

```
data/<business>/*.csv ──► CsvFolderAdapter ──► ImportResult ──► Store.save_import ──► SQLite
                          (normalise, validate,   (models +                (one DB transaction:
                           check references)       rejected rows)           all or nothing)
```

- **CSV format:** one folder per business, one file per entity (`business.csv` required;
  `accounts`, `counterparties`, `payees`, `transactions`, `invoices`, `bills` optional).
  Headers are the schema field names. Money may contain `S$`, `$` and thousands commas. Dates are
  ISO or Singapore day-first (`DD/MM/YYYY`). US month-first dates are rejected as ambiguous.
- **Accrual inputs (chunk 11), optional and not warned when missing:** `opening_balances`
  (`as_of, line, amount`; lines = `schemas.BalanceLine`), `inventory_snapshots` (`date, value`),
  `fixed_assets`, `loans` + `loan_schedule` (`loan_id` must exist in `loans`), `payroll_runs`
  (`period` = `YYYY-MM`). Invoices and bills have an optional `gst` column (the GST inside the
  GST-inclusive `amount`; default 0). Files without an `id` are de-duplicated on their natural key
  (`line`, `date`, `period`, `loan_id + instalment_no`). Row validators reject a schedule row whose
  interest + principal ≠ instalment, a payroll run whose gross ≠ net + employee CPF, and a residual
  value above cost. Two whole-file warnings: mixed `as_of` dates, or an opening balance sheet that
  doesn't balance (`schemas.balance_difference`). The store keeps these in six read-only tables
  (integer cents, `business_id` in every key and query). No tool reads them yet: chunk 12 builds
  the statements.
- **Bad rows** become `RejectedRow`s (file, line, reason, raw values with account numbers
  masked). The rest of the file still loads.
- **Store:** stdlib `sqlite3`, no ORM. Money is `INTEGER` cents (`to_cents` / `from_cents` are the
  only conversion points). Dates are stored as ISO text.
- **Sandbox bank** (`sandbox/bank.py`) shares the same database. Executed payments and
  receipts are written as ordinary `Transaction` rows with `source="sandbox"`, so
  balance = opening balance + Σ transactions, and analysis and forecasts see sandbox activity with
  no extra code. Each business has its own simulated clock (`today`, `advance`). Payments execute
  only when `pay_on <= today`.
- Sandbox-posted transactions are categorised as they are posted (chunk 4a), with the same
  rules as at import (`categorize.classify`): a payment against a bill carries the supplier as
  counterparty, so it gets the supplier's default category or `cogs`. What no rule matches stays
  `uncategorised` and is flagged downstream.

## Ingest pipeline (chunk 2)

`ingest_folder(store, path)` in `src/copilot/ingest.py` is the one entry point for bringing a
business in: adapter → `Store.save_import` → `categorise`. It returns an `IngestReport` holding
the import result (including rejected rows) and the categorisation summary. See
`algorithms.md` for the categorisation rules and the synthetic data generator.

## The schema contract (`src/copilot/schemas.py`)

Every layer exchanges the models defined here, so the conventions are enforced in one place:

- **Money** is `Decimal` with at most 2 decimal places. Floats and bools are rejected at
  validation time, so a float can't slip in from a CSV parser or an LLM tool call. In SQLite,
  money will be stored as integer cents (converted in `store.py` / `sandbox/`).
- **Displaying money:** every amount shown to a user goes through `schemas.sgd()` (`S$1,234.56`, `-S$13,260.76`). A test fails if any message formats money with a bare `:,.2f`, which is how alert messages lost their currency before (fixed 2026-10-04).
- **Sign convention:** `Transaction.amount` is signed (+ in, − out) and never zero. Invoice, bill
  and payment amounts are positive. Their direction comes from the entity type.
- **Dates:** business dates are plain `date` values (local UTC+8). Timestamps must carry the +08:00
  offset.
- **Categories:** each `TransactionCategory` maps to a `CategoryGroup` (revenue, cogs, opex,
  financing, non_operating, uncategorised). Margin metrics use the group, so adding a category
  means adding its group mapping (a test enforces full coverage).
- **Derived states are not stored:** e.g. "overdue" is computed from `due_date` and the clock.
- **Domain results:** every domain function returns `DomainResult[T]` with `value`, `drivers`,
  `data_coverage` and `warnings`.
- All models are immutable and reject unknown fields (`frozen=True, extra="forbid"`).

## Tool interface and the policy gateway (chunk 3b)

The agent never calls a tool, the store or the sandbox directly. Its only route is
`policy.gateway.Gateway`, which matches the layer order (policy sits above tools):

```
agent (3c) ──► Gateway.on_user_message(actor, text)   every user message, BEFORE the LLM
           ──► Gateway.specs(actor)                     tool list for this role
           ──► Gateway.call(actor, tool, args)          every tool call the LLM makes
                   │ validate args → check role → (write) guard → restate → confirm?
                   ▼
               tools/ (read_tools, write_tools) ──► domain modules / store / sandbox
```

**A tool declares** (`tools/registry.py`): `name` (verb_noun), `description` (written for the
LLM), `input_model` (strict, `extra="forbid"`), `min_role`, `kind` (read/write), `run`, and for
writes `describe` (a plain-language restatement built by code) and `needs_confirmation`.
`Gateway.specs(actor)` gives the LLM only the tools that role may use.

**Tools in 3b:**

| Tool | Kind | Min role | Confirmation |
|---|---|---|---|
| get_metrics, get_cash_position, forecast_balance, get_alerts, get_obligations (4b-1), get_cash_summary, run_what_if, recommend_actions (4b-2), list_payees, list_bills, list_invoices | read | viewer | no |
| find_financing, list_applications (4c) | read | viewer | no |
| draft_reminder | write | staff | no (saves a draft only; nothing is sent) |
| set_cash_floor (4b-1), prefill_application (4c) | write | staff | no (saves only) |
| schedule_payment, submit_application (4c) | write | owner | yes: `confirm <4-digit code>` |

**What 3c must do with results:**
- `ToolResult.for_llm()` is what goes back to the LLM: external text is wrapped as
  `<untrusted>…</untrusted>`, account numbers are masked, money is exact text. The confirmation
  code is never included.
- When `ToolResult.pending` is set, the UI shows `pending.prompt` to the user directly
  (the restatement plus "Reply 'confirm 1234' to proceed"), not through the LLM's reply.
- Call `on_user_message` on every user message first. A `Resolution` (executed / scheduled /
  blocked / cancelled / ...) is shown to the user. If it was a cancellation, the message is
  then handled normally by the LLM, because the user may have asked something else.
- `Actor` (user, role, business, session) comes from the session, never from chat.

## Agent loop and UI (chunk 3c)

```
ui/app.py ──► agent.handle(message, session) ──► Gateway.on_user_message   (before any LLM call)
     │                    │                  └─► LLM.complete ⇄ Gateway.call (≤ 6 rounds)
     └─► agent.views (read-only panels, also through the Gateway)
runtime.open_scenario(folder, role) builds the Session: in-memory store + sandbox + Gateway + LLM
```

- **Provider interface** (`agent/llm.py`): neutral `Message`, `ToolCall`, `LLMResponse` and an
  `LLM` protocol, `complete(system, messages, tools)`. Two mocks implement it:
  - `ScriptedLLM` (tests): replays listed responses and records what it was sent.
  - `RuleBasedLLM` (demo): keyword intents that call tools in a fixed order and write
    answers only from tool results.
  The real model, `ClaudeLLM` (chunk 5), is one more class; see "The Claude backend" below.
- **`handle`** (`agent/loop.py`), step by step:
  1. Empty or over-long messages are answered without the LLM.
  2. A pending action is resolved first. A confirmation's result is returned as a system
     notice and the LLM isn't called. After a cancellation, the message goes on to the LLM
     unless it was only "yes", "no", "cancel" or "confirm …".
  3. Then up to 6 LLM rounds, each tool call going through the gateway.
  4. If the LLM raises an error or runs out of rounds, the reply is a fixed fallback.
- **`AgentReply`**: `text` (the LLM's words), `notices` and `pending_prompt` (written by the
  system), `trace` (tool + outcome).
- **`runtime.py`** is the composition root. The UI imports only `agent`, `runtime` and
  `schemas` (checked by `test_isolation.py`).
- **Streamlit:** each rerun runs on a new thread, so the demo store is opened with
  `any_thread=True`. Each browser session has its own in-memory database, used by one rerun
  at a time.

## The Claude backend (chunk 5)

Decided 2026-10-06: **Claude Sonnet 5.5 (`claude-sonnet-5-5`)** for development, evals and the
demo. `agent/claude.py` is the only module that imports `anthropic`.

```
runtime.make_llm("claude") ──► ClaudeLLM.complete(system, messages, tools)
                                 │ to_api_messages: neutral history → Messages API turns
                                 ├─► client.beta.messages.create(...)
                                 │ from_api_response: text + tool_use → LLMResponse(raw=blocks)
                                 └─► usage counter (tokens, US$ estimate for the eval)
```

- **Settings** (env vars or `.env` at the repo root; a real env var wins): `ANTHROPIC_API_KEY`
  (required), `COPILOT_MODEL` (default `claude-sonnet-5-5`), `COPILOT_EFFORT` (default
  `medium`; kept after the chunk-6 comparison below). Switching the model is one env change.
- **Conversion.** user → text turn; assistant → text block (omitted when empty, which the API
  rejects) + `tool_use` blocks; consecutive `tool` messages → one user turn of `tool_result`
  blocks. The loop's `[System] …` notices stay assistant turns (the API merges same-role turns).
  Tool specs are already in the API's shape (`ToolRegistry.specs_for`). There's no `strict`
  mode in v1: the gateway validates every argument anyway.
- **Request:** `max_tokens` 16,000, adaptive thinking, `output_config.effort`, prompt caching
  with two breakpoints (one on the last tool, chunk 6; top-level automatic caching for the
  conversation), `fallbacks="default"`, betas
  `thinking-binding-controls-2026-08-01` and `server-side-fallback-2026-07-01`. Client timeout
  60 s, 2 SDK retries (429/5xx). Any exception still becomes the loop's fixed `FALLBACK`.
- **Preserved thinking.** Sonnet 5.5 signs its thinking blocks, and they must go back unchanged
  on the next step of the tool loop. `LLMResponse.raw` carries the reply's raw blocks, and the
  loop stores them as `Message.provider_blocks` **only if the output guard left the text
  unchanged**, so a blocked reply (e.g. one containing the canary) never returns to the model
  through the raw copy. History can still change legitimately (a rewritten reply, or the system
  prompt's date after a clock advance), so `block_binding.prefix_mismatch_behavior: "drop_block"`
  tells the API to drop the stale reasoning instead of returning a 400.
- **Stop reasons.** `refusal` (after the server-side fallback) → a fixed polite reply;
  `max_tokens` → `ResponseTruncated` → the loop's fallback. Thinking blocks are never shown.
- **Offline by default.** `open_scenario` still defaults to `RuleBasedLLM`; tests use fakes
  (`test_claude_adapter.py` injects a fake client). `tests/conftest.py` blanks the key for every
  test not marked `live`, and `pytest` deselects `live` (`RUN_LIVE=1 pytest -m live` runs it).
- **UI:** the sidebar's "Assistant" picker offers Claude when a key is found (the default),
  otherwise only the rule-based demo.

Measured on cash_crunch (2026-10-08): three questions (cash, Aug vs Jul revenue, financing) all
matched the ground truth in 6 calls for about US$0.09. From the second call on, about 10k tokens
per call are read from the cache. Red-team suite: 26/26 passed in 66 calls, about US$0.99.
Cache writes dominate that cost, because each case is a new session with its own canary in
the system prompt. Chunk 6 added the tool-list breakpoint below.

**Tool-list cache breakpoint (chunk 6).** Render order is tools → system → messages. The tool
list (~4–6k tokens, by role) is identical for every session with the same role, but the system
prompt carries a per-session canary, so the automatic breakpoint at the end of the conversation
never matched across sessions and every new case rewrote the tools at 1.25×.
`with_tool_breakpoint` sends a copy of the tool list with `cache_control` on the last tool (the
registry's specs are never mutated), so later sessions read the tools at 0.1×. The task suite's
medium run read 840k tokens from cache against 127k written (US$0.65 for 71 calls).

**Effort, low vs medium (chunk 6, task suite, 24 cases, same prompt):**

| Effort | Passed | Cost | Time per case | Failures |
|---|---|---|---|---|
| medium | 22/24 | US$0.65 | 8.8 s | T-AN-02 (case over-specified, since fixed), T-IX-02 (assumed the invoice instead of asking) |
| low | 21/24 | US$0.61 | 8.9 s | T-AN-04 (margin shown as 0.8332), T-IX-03 (correction hit the 6-step limit), T-IX-06 (no tool call) |

Low saves only ~6% and is no faster (tool rounds dominate latency), and it failed a correction
outright, so the default stays **medium**. Rule agreed beforehand: switch only if low passes at
least as many cases, then re-check red-team at low. Run-to-run variation is real: the same case
can pass on one run and fail on the next (T-AN-02, T-IX-02), so one run per level is a sample,
not a verdict.

## Simulated clock and scripted world (chunk 4b-1)

```
ui/app.py "+1 day / +7 days" ──► agent.clock.advance(session, days)
    ──► Gateway.advance_clock(actor, days) ──► policy/scheduler.advance, for each day:
            sandbox.set_today(day)
            WorldScript.replay_day(sandbox, day)        (sandbox/world.py, world_* events)
            for each SCHEDULED payment due: check_scheduled_execution → execute_payment
        then alerts before vs after → new_alerts → ClockReport
runtime.open_scenario loads <scenario>/world_events.csv into the Gateway (WorldScript.load)
```

- **Not an LLM tool.** The clock is a demo control in the sidebar. It isn't in the tool
  registry, so no chat message or imported text can move it (a call named `advance_clock` is
  rejected as an unknown tool). Any signed-in role may use it: time passing isn't a permission,
  and it only runs payments the owner already confirmed.
- **The future is fenced off (R12).** `world_events.csv` holds the scenario's next 13 weeks.
  Only `sandbox/world.py` reads it, only the scheduler replays it, and `runtime.py` hands it to
  the gateway. `test_isolation.py` fails if any module under analysis/, cashflow/, financing/,
  tools/, agent/ or ui/ mentions it. Forecasts see only what has been replayed into the ledger.
- **The world script is simulation config, not business data**, so it doesn't go through an
  adapter. Its rows are still validated (`WorldEvent`), and bad rows are rejected with reasons.
- **Bounds:** 1–28 days per advance, never past the script's last day (2026-12-27).
- **Two kinds of sandbox activity.** `world_*` events (customers, direct debits, the business
  paying bills in its own banking app) bypass policy by design (R13). Copilot payments always
  go through the gateway. Both appear in `sandbox_events`. Scheduler runs are also in the audit
  log as `execute_scheduled_payment` by `system-scheduler`, and each advance as `advance_clock`
  by the user who pressed the button.
- **Categories:** world transactions carry their true category (rent, payroll, sales, …). Anything
  posted without one, including copilot payments, is categorised by the sandbox at posting time
  (decided in 4a). Read tools never re-categorise, so they stay strictly read-only.
- **Personal settings:** `ToolContext` now carries `user_id` (from the actor, never from
  arguments), used by `set_cash_floor` / `get_alerts` for the per-user floor (`alert_rules`
  table, scoped by business and user).

## What-if, recommendations and the funding-need contract (chunk 4b-2)

```
tools/read_tools.py  get_cash_summary  ──► cashflow/summary.cash_summary          (transactions)
                     run_what_if       ──► forecast_13_weeks ──► scenarios.what_if
                     recommend_actions ──► forecast_13_weeks ──► recommend.recommend_actions
                                                     scenarios.apply_changes + forecast.walk
```

- **All read-only, viewer role.** A what-if never touches the store or sandbox. It works on a
  copy of the forecast items. Recommendations *name* follow-up actions (e.g. `draft_reminder`)
  but never run them. Any write still goes through the gateway as usual.
- **`ForecastItem.ref` / `counterparty_id`** link each forecast item to its source record.
  `source="what_if"` marks items a scenario added (never produced by the base forecast).
- **Changes are a discriminated union** (`kind`), validated by Pydantic before the tool runs.
  Unknown fields, float amounts, zero amounts and out-of-range delays are rejected. Ids are
  checked within the session's business, so an id from another business is "not found".
- **Contract for 4c:** `recommend.funding_need(as_of, path, target)` → `FundingNeed`
  (`amount`, `target`, `draw_date`, `repay_date | None`, `duration_days`, `duration_months`,
  `duration_is_lower_bound`, `purpose`, `basis`). Take the need from
  `recommend_actions(...).value.funding_need` (after the non-borrowing plan), or call
  `funding_need` on any balance path (`forecast.balance_path`). `None` means no borrowing is
  needed. The need excludes interest and fees: 4c prices each product for this amount and
  duration. When the user states a need instead ("I need S$50k for 6 months"), 4c builds the
  same model from their numbers.

## Financing (chunk 4c)

```
find_financing ──► forecast_13_weeks ──► financing.ranking.match_financing
                     needs.assess_need (recommend_actions → FundingNeed, or the user's numbers)
                     eligibility.business_facts + check   (every product, with reasons)
                     costs.quote                          (flows, total cost, EIR)
                     forecast.balance_path + find_gaps    (does the loan keep cash ≥ target?)
prefill_application (staff) ──► guard: eligible + need exists ──► store.add_application
submit_application (owner)  ──► guard: draft, same business, eligible NOW ──► confirm code
                            ──► store.mark_application_submitted
```

- **Domain stays pure.** `financing/` never writes. Applications are persisted by the store
  (money in integer cents) in `financing_applications`, scoped by business. Its `status`
  column has a CHECK constraint allowing only `draft` and `submitted`, so "approved" can't be
  stored even by a bug.
- **Catalogue is swappable:** `load_catalogue(path)` is the only entry point.
- **Submission re-prices the stored need** (`application.need_for`), so the confirmation text
  shows the same amount, cost and EIR as the draft.

## Analysis (chunk 4a)

```
get_metrics            ─► metrics.period_metrics      (cash basis)
                          metrics.working_capital     (invoice basis: DSO, DPO, CCC)
                          metrics.customer_concentration (invoice basis)
                          metrics.runway
compare_periods        ─► compare.compare_periods + compare.top_movers
get_expense_breakdown  ─► breakdown.expense_breakdown ─► cashflow.summary.cash_summary (reused)
get_ageing             ─► health.ageing x2 (receivables + payment habits, payables)  (chunk 8)
get_cash_trend         ─► health.cash_trend ─► cashflow.summary.cash_summary      (chunk 8)
get_health_ratios      ─► health.debt_service_cover + health.break_even_sales     (chunk 8)
get_financial_statements ─► statements.financial_statements (accrual)           (chunk 12)
                          ─► statements.only (keeps just the asked-for statement)
get_metrics (accrual block) ─► statements.accrual_margins (whole months only)    (chunk 12)
```

Chunk 12 adds a third basis, **accrual**, in `analysis/statements.py`. It reads the store only
(chunk 11's tables plus documents, transactions and account openings) and never the answer
key. `get_metrics` keeps its cash margins unchanged and adds an `accrual` block beside them
(Daniel, 2026-10-11), so no existing number moved. `reconcile.Settlements` gained `matched`
(document id → transaction id), which the statements use to know which bank line settled
which document.

Chunk 8 also extended `get_metrics` with net working capital (`working_capital(..., sandbox=)`,
the only analysis function that reads the sandbox, for the period-end balance) and
`metrics.supplier_concentration` (shares the `_shares` helper with customer concentration).

- **Two bases, always labelled.** Revenue, costs, margins, net cash flow, movers and the expense
  breakdown are cash basis (bank transactions). DSO, DPO, CCC and concentration need receivables
  and payables, which only invoices and bills hold, so they are invoice basis (decided
  2026-10-05). Every result model has a `basis` field and a basis warning.
- **Historic receivables/payables** come from `reconcile.match_settlements` (when each paid
  document was settled) plus `reconcile.outstanding_at(as_of)`. The same matching rule feeds the
  forecast's customer delays, so the two can't disagree.
- **Default comparison:** the period of the same length just before (`dates.previous_period`):
  whole calendar months map to whole months (Sep → Aug, Q3 → Q2), anything else to the same
  number of days.
- All three tools are viewer-level reads. Counterparty names in movers, concentration and
  unpaid-invoice drivers are `UntrustedText`, so they are wrapped on the way to the LLM.

## Policy hardening and the evaluation layer (chunk 4d)

- **New owner tools:** `send_reminder` (sends a saved draft; reminders now live in the store's
  `reminders` table, status draft → sent) and `mark_invoice_paid` (links a ledger receipt to an
  invoice via `invoice_receipt_links`). New read tools `list_receipts` (customer money not yet
  tied to any invoice, from `reconcile.unlinked_receipts`) and `list_reminders`. `list_invoices`
  now includes each invoice's notes (wrapped).
- **Registry:** `Tool.external_effect` marks tools that move money, change the books or reach an
  outsider; registration fails unless they need confirmation. `policy.roles.CAPABILITY_TOOLS`
  ties each tier capability to its tools (test-checked against the registry and
  `permission-tiers.md`).
- **`copilot/untrusted.py`** holds `wrap_untrusted` and `looks_like_instructions`; it sits at the
  top level so both `tools/render.py` and `agent/prompts.py` use it.
- **Agent loop order:** confirmation check → LLM with tools via the gateway → output guard on the
  model's text → reply. The guard reports interventions through `Gateway.record`, so the agent
  still never touches the store. `Session.canary` is created per session.
- **`runtime.open_scenario(..., also_load=(folder, ...))`** loads extra businesses into the same
  database; the red-team suite uses it for cross-business probes.
- **Evaluation layer (`src/copilot/evals/`)** sits beside the UI on top of the stack: it builds
  sessions with `runtime`, drives them only through `agent.handle`, and then inspects the store
  and audit log to score the outcome. Any `LLM` can be plugged in; `FooledLLM` replays scripted
  attacker behaviour and `RecordingLLM` keeps everything sent to the model for the leak checks.
  `scripts/run_eval.py` is the CLI. The task suite (chunk 6) will reuse the same runner shape.

## Task suite (chunk 6)

`src/copilot/evals/tasks.py` runs `tests/tasks/*.yaml` the same way the red-team runner does:
a fresh `runtime.open_scenario` session per case, user turns through `agent.handle`, then checks
on the reply, the tool trace, the tool results and the audit log. No LLM judge: grading is
deterministic and free (details in algorithms.md → "Grading task answers").

- **Case format:** `capability` (analysis, cashflow, financing, interaction), `scenario`
  (cash_crunch or concentrated_b2b), `role`, `turns` (each with `tools`, `tool_args`,
  `no_tools`, `values`, `any_value`, `any_of`, `excludes`, `asks_question`), and whole-
  conversation `audit` (outcomes in order) and `effects` (exact count of executed/scheduled
  writes; absent = none). `{code}` in a user turn is the real confirmation code.
- **Expected values** come from `ground_truth.json` (`truth`, `truth_sum`) where the truth is
  known, from the tool result for forecast-type values (`tool` + `path`, checked against the
  truth within `tolerance` via `near_truth`), or from a literal with its `source` (an input row).
- **Offline:** pytest runs every case on the rule-based mock. Cases the mock can't do carry
  `mock_skip` with the reason (6: named periods, a year with no data, DIO, a clarification
  follow-up, a correction); `test_a_skipped_case_really_fails_on_the_mock` keeps the skips honest.
- **CLI:** `python scripts/run_eval.py --suite tasks [--llm mock|claude] [--effort low|medium]`
  prints the scorecard by capability; Claude runs add the token/US$ line and seconds per case.

## Execution evidence export (chunk 7)

`src/copilot/evals/evidence.py` turns suite runs into the operation logs of deliverable #6;
`scripts/export_evidence.py` is the CLI (`--llm offline` = fooled + mock, `--llm claude`).

- **Getting the session:** both runners have `run_case_session(case, llm) -> CaseRun`
  (result, finished session, where each turn starts in the history, the replies shown, balances
  before); `run_case` wraps it, so suite behaviour is unchanged.
- **What a case file holds:** the conversation rebuilt from `session.history` (tool calls with
  masked arguments, outcome and message; the tool data in a collapsible block, with the
  `<untrusted>` labels exactly as the model saw them) plus the `AgentReply` notices and
  confirmation prompt; audit rows except plain successful reads; `sandbox.events()`; balances
  before/after; `verify_chain` + head hash for every business in that case's database; Claude
  token use and US$ per case.
- **Output:** `evidence/logs/<mode>/index.md` (header with model, effort, date, commit,
  usage; scorecards; one row per case with write outcomes and head hash), `run.json` (same,
  machine-readable) and `<suite>/<id>.md`. Each export clears its folder's case files first; a
  `--case` run goes to `<mode>-partial/` (ignored by Git), so it can't replace the submitted run.
- **Redaction** (`_Redactor`, applied to the whole case record before writing): "confirm 1234"
  in any form → "confirm ****", the session canary → `[canary]`, every business's full account
  numbers → ••••1234. Bare 4-digit numbers are left alone, so invoice numbers and years survive.
  `tests/unit/test_evidence.py` scans every written file for full numbers (digits only too),
  codes and the canary prefix.
- **Git:** `logs/claude/` and `logs/fooled/` are committed; `logs/mock/` is ignored.
  The demo storyline (`STORYLINE`: T-CF-01, T-CF-06, T-FI-03, RT-IT-01) is starred in the index
  and described in `evidence/video/storyline.md`.

## API (chunk 9) and the planned web dashboard (chunk 10)

```
browser ──cookie──► FastAPI (src/copilot/api/app.py)
                      │  SessionStore: random id -> Session (role, business fixed at sign-in)
                      ├─ GET  /api/dashboard     ─► agent.views.dashboard_panels ─► Gateway.call x8
                      ├─ GET  /api/statements    ─► agent.views.statements ─► Gateway.call  (chunk 12; ?view=as_imported, chunk 13)
                      ├─ GET  /api/adjustments   ─► agent.views.adjustments ─► Gateway.call (chunk 13, read-only)
                      ├─ POST /api/chat          ─► agent.handle (writes -> pending -> confirm <code>)
                      ├─ POST /api/clock/advance ─► agent.clock.advance ─► Gateway.advance_clock
                      └─ GET/POST/DELETE /api/session, GET /api/options
```

- **A second UI, not a new layer.** The API imports only `copilot.agent`, `copilot.runtime`,
  `copilot.schemas` and itself (test_isolation). It calls exactly what Streamlit calls, so every
  panel read is role-checked and audited as the signed-in user, and every write still needs the
  user's own `confirm <code>`.
- **Sessions** (`api/sessions.py`): in memory; the browser holds only a 256-bit random id in an
  HttpOnly, SameSite=Strict cookie on `/api`. Max 20 live sessions (least recently used evicted),
  2 h idle expiry, 40 chat messages per Claude session (429 after). Each request holds the
  session's lock: a `Session` (history, pending action, SQLite connection) isn't thread-safe and
  FastAPI runs sync handlers on a thread pool.
- **Role and business come only from sign-in.** Request bodies reject unknown fields, so a
  smuggled `role` or `business_id` is a 422. Sign-in itself is the same demo picker as Streamlit
  (R11); `COPILOT_API_ROLES` can drop Owner for a hosted demo.
- **Dashboard** = cash, forecast, alerts, metrics (last full quarter), ageing, cash trend, health
  ratios and financing, each `{ok, message, data}`, plus the pending confirmation. Data is the
  domain result in Pydantic JSON mode: money as strings, dates ISO, never floats.
- **Untrusted text** is returned raw (wrapping is only for the LLM). The frontend must show it with
  `textContent`, never `innerHTML` or Markdown (R37, R38).
- **Local by default:** `python -m copilot.api` binds 127.0.0.1. No CORS (the dashboard will be
  served from the same origin). `Cache-Control: no-store` and `nosniff` on every response.

**Chunk 10 (planned):** no-build static HTML/CSS/JS (Chart.js from a CDN) served by this app, so
neither we nor judges need Node.js. Design input from Figma: a 1440-wide desktop frame; states for
loading, empty, error, alert severities, pending confirmation and the viewer role; components with
variants (KPI tile, alert card, chart card, chat bubbles: user, assistant, system notice, pending
confirmation); colour, type and spacing as Figma variables. Shared as PNG exports in `design/`
plus the token values.

## Editing: recorded adjustments and saved assumptions (chunk 13)

```
chat ─► draft_adjustment (staff) ─► adjustments table, status draft      (counts nowhere)
     ─► apply_adjustment / undo_adjustment (owner, confirm <code>) ─► status applied / undone
     ─► save_assumption / remove_assumption (owner, confirm <code>) ─► forecast_assumptions
                                    │
statements.py: _read() lays applied adjustments over copies of the books (view=as_imported skips)
forecast.py:   forecast_13_weeks(use_saved=True) applies active assumptions
```

| Tool | Kind | Min role | Confirmation |
|---|---|---|---|
| list_adjustments | read | viewer | no |
| draft_adjustment | write | staff | no (a draft changes no figure) |
| apply_adjustment, undo_adjustment | write | owner | yes (`external_effect`: changes the books) |
| save_assumption, remove_assumption | write | owner | yes (`external_effect`: changes everyone's forecast) |

- **Store:** two tables, `adjustments` and `forecast_assumptions`, scoped by `business_id`, money
  in cents, never deleted (undo/remove change the status and record who and when).
- **Shared rules** in `analysis/adjustments.py` (open months, allowed lines, effect preview) are
  used by both the tools and `policy/guards.py`, so the guard and the restatement can't disagree.
- **Previews:** `monthly_statements(..., preview=(add, leave_out))` and
  `forecast_13_weeks(..., preview=...)` build the result as if an edit were applied or removed,
  without writing. The confirmation text uses them.
- **Everything downstream follows automatically:** `get_metrics`' accrual block and the API read
  the adjusted statements; alerts, recommendations, financing need and what-if read the forecast
  with saved assumptions. Cash-basis analysis does not change (R44).
- **Evaluation:** task capability `editing` (T-ED-01..06; values = answer key + the known amount
  via the grader's `plus` field); red-team snapshot now includes applied adjustments and active
  assumptions.
