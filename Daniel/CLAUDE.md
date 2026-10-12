# 2026 Shenzhen International FinTech Competition — International Track
# Project: SME Finance Copilot (Topic E)

Project folder for Daniel's entry (code, data, analysis, deck).
Sources of truth for competition facts: `reference/2026Shenzhen Fintech competition.pdf` and
`reference/international-topics-rules-en.docx` (local only; `reference/` is gitignored).
Official site: http://fintechathon.g-ican.com/#/en
Contacts: registration → `fintechathon@ican-x.com` (PDF p.3); general enquiries → `info@ican-x.com` (rules §9).

## Competition context
- **Theme:** "AI as a Financial Participant"
- **Track:** International Track (first year it exists), open to students at universities
  outside China. English only; no Chinese required.
- **Hosts:** Shenzhen University WeBank Institute of Financial Technology, WeBank Co., Ltd.
- **Prize pool:** RMB 750,000 total (RMB 250,000 per track: 1st RMB 100k, 2nd 80k, 3rd 50k,
  Best Innovation 20k, all pre-tax). Strong teams get WeBank fast-track interviews.
- **Finalist package:** travel and accommodation covered, WeBank HQ visit, invitation letter
  issued the day finalists are announced (for visa and NTU approval).

## Key dates (Beijing time, UTC+8)
| Date | Milestone |
|---|---|
| Aug 31, 2026 | Registration opened |
| **Oct 20, 2026, 23:59** | **Registration and submission deadline. Same clock as Singapore (SGT = UTC+8)** |
| Oct 21–22, 2026 | Compliance screening |
| Oct 23–28, 2026 | Online review |
| Oct 31, 2026 | Finalists announced + visa invitation letters |
| Nov 20, 2026 | Check-in and WeBank HQ visit, Shenzhen |
| Nov 21–23, 2026 | Grand Final and Awards Ceremony, Shenzhen |

Registration is by email: download the form from the official site and send it to
`fintechathon@ican-x.com` with subject
`International Track Registration – Country – Team Name – Team Leader's Full Name`.
The organiser confirms within 48 hours. **Our target: registration email sent by Oct 10.**

Submissions can be updated any time before the deadline, and the latest version received wins.
Nothing is accepted after the deadline. **Strategy: submit a complete early version by Oct 17,
then send updates.**

## Team (rules §4)
- Je Hoon Chung (Daniel), NTU, Economics & Data Science
- (add teammates + roles; 3+ members will write code)

Constraints:
- 2–5 full-time students at universities outside mainland China / HK / Macao / Taiwan.
- **At least 60% of members should be non-Chinese nationals**, or the Organizing Committee may move the team to another track.
- One team per person across both tracks.
- **At least one member must attend the Shenzhen final in person** (Nov 21–23), or the team forfeits award eligibility (rules §6).

## Chosen topic: E, SME Finance Copilot
> "A finance copilot for small-business owners, offering financing-option matching,
> cash-flow management and alerts, and business financial analysis."
> — `international-topics-rules-en.docx`, §2

Three capabilities the judges will look for, taken directly from that line:
1. **Business financial analysis**: read the books, compute key metrics, explain what they mean.
2. **Cash-flow management and alerts**: monitor, forecast, warn, recommend fixes.
3. **Financing-option matching**: match an SME to suitable financing products and compare true costs.

The theme, "AI as a Financial Participant", asks for "an AI agent capable of completing real
tasks in a financial scenario" (rules §1). The rules do not say the agent must make payments or
other write actions. **Our interpretation:** the agent proposes actions and, with explicit user
confirmation, carries them out (incl. simulated payments in the sandbox), rather than being a
dashboard or a chatbot that only answers questions. Two parts of the rules support this:
§5 #5 asks for a "permission-tier implementation" and §5 #6 for "simulated-account/sandbox
operation logs". Payments were kept by choice (2026-10-04) as the clearest way to demonstrate
the security guards. Note: the threat list in the Scoring and Security sections below
(induced transfers, etc.) is also our own assumption; the rules give only the weights.

Topic E is not the on-chain topic, so the 0–5 challenge bonus (Topic F only) is not available to us.
Everything else is scored identically across topics.

## Scoring (same for all topics, rules §3)
The rules give only the weights. The third column is **our own design goal (an assumption,
not stated in the rules)**. No competition-provided simulated environment is assumed; we ship
our own sandbox and catalogue.

| Weight | Criterion | Our design goal (assumption) |
|---|---|---|
| 40% | Task completion | Agent completes scripted tasks correctly on our sandbox data. Correctness beats breadth. |
| 30% | Security & compliance | Withstand induced transfers, data extraction, privilege escalation and prompt injection (our red-team suite). It also has its own required deliverable (the security self-assessment report). |
| 30% | Innovation & interaction | Real-world value, dialogue efficiency, clarification, correction, fallback. |
| 0–5 pts | Challenge bonus | On-chain only. **Not available on Topic E.** |

Treat permission tiers and risk handling as first-class build work, not documentation written at the end.

## Submission checklist (rules §5, all six required)
| # | Deliverable | Where it lives in this repo |
|---|---|---|
| 1 | **Technical documentation**: system architecture, core algorithm description, security design | `docs/technical/` |
| 2 | **Presentation deck**: final presentation capped at 10 minutes | `deck/` |
| 3 | **Demo video**: listed as optional, max 5 minutes. **Treat as required**, because #6 needs one for Topic E | `evidence/video/` (link) |
| 4 | **Source code**: README, **GitHub repository link**, deployment instructions, test cases | repo root, `README.md`, `tests/` |
| 5 | **Security self-assessment report**: permission-tier implementation + known-risk list | `docs/security/` |
| 6 | **Execution evidence**: for Topic E, simulated-account / sandbox operation logs plus a demo video (on-chain tx hashes are the Topic F version, not ours) | `evidence/logs/` |

## Architecture
Six layers plus a UI on top. Each layer calls only the layers below it.

1. **Adapters** (`adapters/`): convert any external data format into the models in `schemas.py`.
2. **Store** (`store.py`): SQLite repository. Every query requires `business_id`.
   **Sandbox** (`sandbox/`) sits beside it in the same SQLite DB: simulated bank accounts, a ledger,
   and a simulated clock ("today", which can be advanced). Executed write actions (payments,
   invoice marked paid, etc.) post real ledger entries, so balances and forecasts change.
   This is what produces the "simulated-account / sandbox operation logs" for deliverable #6.
3. **Domain modules** (`analysis/`, `cashflow/`, `financing/`, plus shared `categorize.py`, `reconcile.py`):
   pure, deterministic Python. They return typed result models and never call the LLM.
4. **Tools** (`tools/`): thin wrappers that expose domain functions to the LLM.
5. **Policy** (`policy/`): guards every write action (permission tiers, limits, confirmation, audit log).
6. **Agent** (`agent/`): LLM orchestration loop, system prompt, conversation state.
   Single entry point `agent.handle(message, session)` is the only thing the UI calls.

**UI** (`ui/`): Streamlit chat plus side panels (balance, alerts, pending confirmations) for v1.
It only calls `agent.handle(...)` and read-only views, so a web front end can replace it later
without touching the agent.

How the features connect:
- Analysis metrics feed financing eligibility (revenue, months operating, margins).
- The cash-flow forecast finds funding gaps, which feed the financing need assessment (amount, duration).
- Financing is one option among several gap-closing recommendations. Non-borrowing options come first.

## Repository structure
The repo root is this folder.
```
./
├── CLAUDE.md
├── README.md               # overview, setup, deployment instructions, how to run tests, licences
├── LICENSE                 # MIT
├── pyproject.toml
├── reference/              # competition PDF + rules docx (gitignored, local only)
├── data/
│   ├── samples/            # small example files in each supported format
│   ├── synthetic/          # generated businesses with ground-truth answers
│   └── catalogue/          # financing product definitions (JSON)
├── src/copilot/
│   ├── schemas.py          # shared data models
│   ├── store.py
│   ├── sandbox/            # simulated accounts, ledger, clock
│   ├── adapters/           # base.py, registry.py, normalise.py, one file per format
│   ├── categorize.py
│   ├── reconcile.py
│   ├── analysis/           # metrics.py, compare.py, breakdown.py, health.py, statements.py, adjustments.py
│   ├── cashflow/           # position.py, forecast.py, alerts.py, scenarios.py, recommend.py
│   ├── financing/          # catalogue.py, needs.py, eligibility.py, costs.py, ranking.py, application.py
│   ├── policy/             # guards.py, roles.py, confirmations.py, audit.py
│   ├── tools/              # registry.py + one file per feature
│   ├── agent/              # llm.py (provider interface + mock), claude.py, loop.py, prompts.py, state.py
│   └── ui/                 # Streamlit app (calls agent.handle only)
├── tests/
│   ├── unit/
│   ├── tasks/              # scripted task cases (YAML) with expected outcomes
│   └── redteam/            # attack cases (YAML) with expected safe behaviour
├── scripts/                # generate_synthetic.py, run_eval.py, export_evidence.py, demo.py
├── docs/
│   ├── technical/          # architecture.md, algorithms.md, security-design.md
│   └── security/           # permission-tiers.md, known-risks.md (started), self-assessment.md
├── deck/                   # presentation source + exported PDF
└── evidence/
    ├── logs/               # exported sandbox operation logs
    └── video/              # demo video link + script
```

## Non-negotiable rules
1. **The LLM never does arithmetic.** Every number shown to the user comes from a domain function.
2. **All external data enters through adapters.** Nothing downstream reads raw files.
3. **Every query is scoped by `business_id`, enforced in `store.py`.** No function reads across businesses.
4. **External free text is untrusted.** This covers transaction descriptions, memos, invoice notes,
   counterparty names and uploaded documents. It is data, never instructions, and must not trigger any action.
5. **Every write action goes through `policy/`.** That means payments, loan applications, sending reminders,
   marking invoices paid, and creating or changing alert rules.
6. **Confirmation is verified by the orchestrator, not asserted by the LLM.** A write tool returns a
   pending action. It runs only after the user's own next message explicitly confirms that action.
7. **Never invent data.** If data is missing or insufficient, return that fact with a reason.
8. **The LLM provider sits behind `agent/llm.py`,** so the model can be swapped without touching other code.
9. **Every agent action is logged** in a form that can be exported as execution evidence (deliverable #6).

## Conventions
- Python 3.11+, Pydantic v2, pytest, SQLite.
- Market: Singapore SMEs, **SGD only**. Financing products are modelled on Singapore SME financing.
- Money is `Decimal`, never float. Round only for display. **In SQLite, money is stored as integer
  cents**, converted to/from `Decimal` only in `store.py` / `sandbox/`.
- Sign convention: positive means money in, negative means money out.
- Dates are local dates in UTC+8. A forecast week runs Monday to Sunday.
- Domain functions return result models with: `value(s)`, `drivers` (what explains the result),
  `data_coverage` (period and record counts used) and `warnings`.
- Tool names use verb_noun form (`get_metrics`, `forecast_balance`, `find_eligible_products`).
  Docstrings are written for the LLM: when to use the tool, what each argument means, what it returns.
- Never silently drop bad data. Record rejected rows with reasons.
- CSV input format: one folder per business, one file per entity, headers = schema field names
  (`business.csv` required). Dates are ISO or `DD/MM/YYYY`. Example: `data/samples/demo_business/`.
  Details in `docs/technical/architecture.md`.
- When a design decision affects architecture, algorithms or security, add a note to the
  matching file in `docs/technical/` in the same session. Documentation grows with the code.

## Feature specs

**v1 scope (early submission, Oct 17)** vs **deferred (only if time allows)**. Anything marked
*deferred* must not block v1. Agreed cuts (2026-10-01):
- Analysis: **cash basis only** in v1. Accrual basis *deferred*.
- Inputs: **one CSV format per entity** (bank transactions, invoices, bills, payees, etc.).
  Extra adapters/formats *deferred*.
- Alerts: **threshold, shortfall, overdue receivables** in v1. Payment-behaviour change,
  anomalies and alert grouping *deferred*.
- Security: payee allowlist, limits, tiers, confirmation and audit in v1. Verification of
  new/changed bank details *deferred* (record it in known-risks.md).
- Reconciliation (`reconcile.py`) *deferred*.

### 1. Business financial analysis (`analysis/`)
v1 uses cash basis and states it. (*Deferred:* accrual basis when invoices and bills are
available.) Always state which basis was used.

| Metric | Definition |
|---|---|
| Revenue | Invoiced sales in period (cash basis: categorised sales receipts) |
| Gross margin | (Revenue − COGS) / Revenue |
| Operating margin | (Revenue − COGS − operating expenses) / Revenue |
| DSO | Accounts receivable at period end / Revenue in period × days in period |
| DPO | Accounts payable at period end / Purchases in period × days in period |
| Cash conversion cycle | DSO + DIO − DPO (omit DIO, with a warning, if there is no inventory data) |
| Runway (months) | Cash / average monthly net outflow over the last 3 months (only when net outflow > 0) |
| Customer concentration | Largest customer's revenue / total revenue |
| Expense breakdown | Spend by category, with period-over-period change |
| Net working capital *(chunk 8)* | Cash at period end + receivables − payables |
| Supplier concentration *(chunk 8)* | Largest supplier's bills / all supplier bills |
| Receivables / payables ageing *(chunk 8)* | Unpaid amount by days past due (not due, 1–30, 31–60, 61–90, 90+); per-customer average days paid late |
| Cash trend *(chunk 8)* | Monthly revenue, gross burn, net; last 3 vs previous 3 months; revenue volatility (std dev / mean) |
| Debt service cover *(chunk 8)* | Operating cash after tax and drawings / loan repayments, last 12 months (none if no loan) |
| Break-even sales *(chunk 8)* | Monthly operating expenses / gross margin, last 3 months, vs actual sales |

Required functions: metrics for a period, comparison between two periods, expense breakdown,
top movers (largest changes and their causes).

### 2. Cash-flow management & alerts (`cashflow/`)
- **Position:** current balance across accounts, as of a date.
- **Summaries:** inflows and outflows by category and period, plus net cash flow.
- **Obligations calendar:** known upcoming bills, payroll, rent, tax, loan instalments and expected receipts.
- **Forecast:** rolling 13-week projection built from:
  1. scheduled items with due dates,
  2. recurring patterns detected from history,
  3. expected receipts, timed by each customer's historical payment delay (not the due date).
  Outputs: weekly balances, the low point (date and amount), runway, and the assumptions used.
- **Alerts (v1):** threshold (balance below a floor), shortfall (a named obligation can't be covered),
  overdue receivables. Ranked by urgency × impact.
  *Deferred:* payment-behaviour change, anomalies (duplicates, unusual amounts, supplier price
  jumps), grouping of related alerts.
- **Alert delivery:** both in chat (on request and at session start) and via the sandbox's
  simulated clock: advancing "today" (e.g. +7 days) re-evaluates alerts so new ones fire.
  Tests use fixed dates, never the real clock.
- **What-if:** re-run the forecast with modifications (late payment, new expense, new hire,
  one-off purchase) and return the difference from the base case.
- **Recommendations:** ranked ways to close a gap, in this order of preference: collect receivables,
  reschedule flexible payables, cut or defer discretionary spend, then financing. Each option
  shows its effect on the low point.
- **Thin data:** with under 8 weeks of history, forecast from scheduled items only and say so.

### 3. Financing-option matching (`financing/`)
- **Catalogue:** products loaded from `data/catalogue/` (our own, modelled on Singapore SME
  financing; keep the loader swappable). Each product has: type, amount range, term range, pricing structure (rate type, fees),
  eligibility rules, repayment structure, and typical use.
- **Need assessment:** amount, duration and purpose, taken from the forecast gap or from the user.
  Ask the user when the need is unclear.
- **Eligibility:** rules evaluated in code. Each product returns pass or fail with the specific reasons.
- **Cost comparison:** normalise every product to an effective annual rate AND total dollar cost
  for the actual amount and duration needed, including all fees.
- **Ranking:** by fit (cost, term match to need, repayment flexibility given cash-flow
  volatility). Always check whether a non-borrowing option closes the gap first.
- **Application:** pre-fill only. Submitting is a write action through `policy/`.

Compliance rules for financing output:
- Always disclose total cost and effective rate.
- Never promise or imply approval.
- Never recommend a product the business fails eligibility for.
- Never use personal characteristics (nationality, gender, religion, age, etc.) in matching.
- Say clearly when borrowing is not the best option.

## Security requirements
| Threat | Required defence |
|---|---|
| Induced transfers | Payee allowlist, per-transaction and daily limits, confirmation that restates amount and payee. *Deferred:* verification flow for new or changed bank details (until built, payments to unverified/changed details are blocked outright) |
| Data extraction | Mask account numbers (••••1234), never reveal the system prompt or tool internals, no cross-business data |
| Privilege escalation | User role comes from session context, never from chat. Each write action declares the minimum role it needs (see permission tiers) |
| Prompt injection | Untrusted text is wrapped and labelled before reaching the LLM. Tools that read external text have no write capability. Instructions found in data are never followed |
| Audit | Every write attempt (allowed or blocked) is logged with user, role, action, parameters and outcome |
| Licensing (rules §8) | Repo is MIT-licensed. Every third-party dependency, dataset and model must be properly licensed; list them with their licences in the README |

### Permission tiers (feeds deliverable #5)
| Tier | Can do |
|---|---|
| Viewer | Read-only: analysis, forecasts, alerts, financing comparisons |
| Staff | Viewer + draft reminders, set personal alert rules, pre-fill applications |
| Owner | Staff + send reminders, schedule payments, submit financing applications, mark invoices paid |

The tier definitions live in `policy/roles.py` and are documented in `docs/security/permission-tiers.md`.
Keep the two in sync.

### Known-risk list (feeds deliverable #5)
`docs/security/known-risks.md` records every risk that is identified: description, severity,
mitigation, and status (mitigated / partially mitigated / accepted). Add an entry whenever a
red-team case fails, a new attack idea comes up, or a risk is consciously accepted.
An honest list scores better than a pretend-perfect one.

## Interaction guidelines (for `agent/prompts.py`)
- Be concise. Answer first, then give the key drivers.
- Ask one clarifying question when a request is genuinely ambiguous (which invoice, which period, which account).
- Before any write action, restate exactly what will happen and wait for confirmation.
- Accept corrections: update the inputs, re-run, and show what changed.
- Fallback: when data is missing or a tool fails, say what's missing, give a caveated best answer
  if one is possible, and never invent numbers.

## Testing
- **Unit tests** for every domain function, adapter, and policy guard.
- **Task suite** (`tests/tasks/`): each YAML case holds a conversation, the expected tool calls and the expected answer values.
- **Red-team suite** (`tests/redteam/`): each YAML case holds an attack and the expected safe behaviour (no write action executed, no data leaked).
- Synthetic data in `data/synthetic/` includes ground truth, so results can be scored automatically.
- A feature is not done until its tests pass. Every bug found gets a regression test.
- Test cases are a required deliverable (#4), so keep them readable and documented.

## Execution evidence (deliverable #6)
- `policy/audit.py` logs every tool call and write attempt: timestamp, session, role, tool,
  parameters (sensitive values masked), outcome, and blocked reason if any.
- `scripts/export_evidence.py` runs the task and red-team suites against the sandbox and
  exports readable operation logs to `evidence/logs/`.
- The demo video should show the same scenarios that appear in the exported logs.

## Commands
```
python -m venv .venv            # then activate (Windows: .venv\Scripts\activate)
python -m pip install -e ".[dev]"
ruff check .
ruff format .
pytest
python scripts/generate_synthetic.py
python scripts/run_eval.py --suite tasks
python scripts/run_eval.py --suite redteam
python scripts/export_evidence.py
python -m copilot.api            # API on 127.0.0.1:8000/docs (needs ".[api]")
```

## Open questions (do NOT hard-code assumptions about these)
- ~~LLM provider/model~~ **Decided 2026-10-06: Claude Sonnet 5.5 (`claude-sonnet-5-5`) for
  development, evals and the demo** (not Opus). Prompt caching on; Console spend cap. Key in
  `.env` at the repo root. Model/effort switchable via `COPILOT_MODEL` / `COPILOT_EFFORT`.
  An HF backend stays deferred.
- How judges run it: their own API key (documented in README) vs. a hosted demo (needs a spend cap).

## Working rules for Claude Code
- Read this file at the start of every session.
- Present a plan and wait for approval before writing code.
- One chunk per session per coder. Parallel work only on the streams listed under Status
  (3a/3b, then 4a–4d); don't build ahead of the current chunk otherwise.
- If the spec is ambiguous, ask rather than guess.
- Run the tests before declaring a task done, then update the status below.

## Status

### Build (thin slice first, then parallel streams)
- [x] 0. Repo skeleton, pyproject, LICENSE (MIT), schemas: Business, Account, Transaction,
      Counterparty, Invoice, Bill, Payee, ScheduledPayment, FinancingProduct, EligibilityRule
- [x] 1. CSV adapters (one format per entity) + store (integer cents, `business_id` scoping)
      + sandbox (accounts, ledger, simulated clock)
- [x] 2. Synthetic Singapore SME generator (with ground truth) + categorisation.
      Scenarios: `cash_crunch` (forward low −S$18.1k, week 6; −S$17.8k since chunk 11) and `concentrated_b2b`.
      Thin-data and prompt-injection fixtures are built in 4b and 4d, where they're used.
- [x] 3. **Thin end-to-end slice (target Oct 8)**, split in three. Keep each part thin; depth
      belongs to chunk 4.
  - [x] 3a. Thin domain: core metrics (revenue, gross margin, runway), basic 13-week forecast
        (scheduled items + recurring costs), threshold alert. Scored against `ground_truth.json`.
  - [x] 3b. Thin security path: roles, confirmation flow (pending action, runs only after the
        user's own next message confirms), payee allowlist + limits, audit log, tool registry.
        **3b fixes the tool interface** (name, inputs, minimum role, read vs write) that 3c uses.
        Done: `policy.gateway.Gateway` is the agent's only route to tools (`call`, `specs`,
        `on_user_message`); limits S$75k/payment, S$100k/day; confirm = `confirm <4-digit code>`;
        write tools `schedule_payment` (owner) + `draft_reminder` (staff). How 3c must use it:
        `docs/technical/architecture.md` → "Tool interface and the policy gateway".
  - [x] 3c. Agent + screen: `agent.handle(message, session)` loop on a mock LLM, minimal
        Streamlit chat, end-to-end tests. Depends on 3a + 3b.
        Done: `ScriptedLLM` (tests) + `RuleBasedLLM` (demo, no API key); `runtime.open_scenario`
        builds sessions; `streamlit run src/copilot/ui/app.py` (demo user picker, fresh
        in-memory sandbox per session). Chunk 5 only needs a new class implementing `LLM`.
      3a and 3b can run in parallel; 3c comes last.
- [ ] 4. Parallel deepening, one stream per coder:
  - [x] 4a. Analysis: full v1 metrics, period comparison, expense breakdown, top movers.
        DSO / DPO / CCC (no DIO, warned) and concentration are **invoice basis** (AR/AP rebuilt
        via `reconcile.match_settlements` + `outstanding_at`); revenue, margins, movers and
        breakdown stay cash basis; every result has a `basis`. Tools: `get_metrics` (extended),
        `compare_periods` (+ top movers with counterparty causes), `get_expense_breakdown`
        (reuses `cash_summary`). Default comparison = previous period of equal length. The
        sandbox now categorises every posting (`classify`), so read tools never write.
        cash_crunch Aug vs Jul: revenue −S$85,702.43 (Bayfront 1 receipt vs 2), DSO 37.2→51.5.
  - [x] 4b. Cash flow, split in two (2026-10-04):
    - [x] 4b-1. Scripted world (`world_events.csv`, replayed by `sandbox/world.py`), clock
          advance via `Gateway.advance_clock` (UI only, not an LLM tool) that runs scheduled
          payments after re-checking guards (R8 closed), scheduled payments in the forecast,
          3 v1 alerts ranked severity-first then SGD x urgency, `new_alerts`, obligations
          calendar (`get_obligations`), personal floor (`set_cash_floor`, staff).
    - [x] 4b-2. Cash-flow summaries (`get_cash_summary`), what-if (`run_what_if`: 6 change
          kinds on a copy of the forecast items), recommendations (`recommend_actions`:
          collect → reschedule → cut, greedy plan, then borrow). Gap target = zero + optional
          buffer (agreed 2026-10-05). **4c starts from `recommend.FundingNeed`** (amount,
          draw/repay date, duration, lower-bound flag; None = no borrowing needed): see
          architecture.md → "What-if, recommendations and the funding-need contract".
          cash_crunch: chase INV-1062 closes Nov; Dec needs S$13,260.76 for ≥22 days.
  - [x] 4c. Financing: catalogue (7 illustrative products, fictional lenders), needs
        (forecast need after the non-borrowing plan, or user-stated), eligibility with
        reasons (unknown = not eligible), costs (total S$ + EIR via XIRR), ranking (keeps
        cash ≥ target, then cost, then flexibility if volatile), `find_financing`,
        `prefill_application` (staff) and `submit_application` (owner + confirm;
        statuses draft/submitted only). cash_crunch: trade financing S$172.58, 16.44%.
  - [x] 4d. Policy hardening + tool registry + red-team cases. New owner tools
        `send_reminder` (no recipient arg, 1/invoice/7 days) and `mark_invoice_paid` (links a
        ledger receipt, moves no money); `external_effect` tools must be confirmed; tier table
        test-synced with the registry. R7 closed (imported names wrapped); tool messages and
        system notices wrapped (R21, found by the suite); instruction-like text flagged and
        audited; output guard (canary, code stripping, account masking); hash-chained audit.
        Fixture `prompt_injection` (cash_crunch + attacks). 26 YAML cases in `tests/redteam/`,
        run by `src/copilot/evals/redteam.py`: fooled-model mode (structure) and any-LLM mode
        (universal checks). `python scripts/run_eval.py --suite redteam` prints the scorecard;
        **chunk 5 adds `--llm claude`, chunk 6 adds `--suite tasks`.**
- [x] 5. Real LLM backend: `agent/claude.py` `ClaudeLLM` (Sonnet 5.5, adaptive thinking at
      effort `medium`, prompt caching, signed thinking replayed verbatim unless the output guard
      changed the reply, `drop_block`, server-side refusal fallback). `runtime.make_llm("claude"
      | "mock")`; UI "Assistant" picker; `run_eval.py --llm claude` prints tokens + US$.
      Offline tests blank the key (conftest); `RUN_LIVE=1 pytest -m live` for the real call.
      Measured 2026-10-08: cash_crunch cash / Aug-vs-Jul / financing answers match ground
      truth (~US$0.09); **red-team 26/26 with Claude** (66 calls, ~US$0.99).
- [x] 6. Task and red-team suites running end to end. 24 YAML cases in `tests/tasks/`
      (analysis 5, cash flow 9 incl. confirmed payment + reminder, financing 4 incl. confirmed
      submission and staff limits, interaction 6: clarification, correction, missing data,
      viewer fallback) on cash_crunch + concentrated_b2b, run by `src/copilot/evals/tasks.py`.
      Values from `ground_truth.json`; every S$/% in a reply must trace to a tool result
      (grounding check). pytest = mock only (18 run, 6 `mock_skip` with reasons).
      `run_eval.py --suite tasks --llm claude [--effort ...]` prints tokens, US$ and s/case.
      Tool-list cache breakpoint added (`with_tool_breakpoint`). Measured 2026-10-08 on Claude:
      medium 22/24, US$0.65, 8.8 s/case; low 21/24, US$0.61 → **default stays medium**.
      Findings: model added two shares itself (R34, prompt fixed), assumed an invoice instead of
      asking (R35), low effort hit the step limit on a correction (R36).
- [x] 7. Evidence export. `scripts/export_evidence.py` (`--llm offline` = fooled red-team +
      mock tasks; `--llm claude`) → `evidence/logs/<mode>/` index.md + run.json + one Markdown
      file per case (conversation, tool calls, audit write trail with role/reason, sandbox
      operations, balances before/after, audit chain check + head hash per business). Redaction:
      codes → `confirm ****`, canary, full account numbers. `claude/` + `fooled/` committed,
      `mock/` ignored. Storyline T-CF-01 → T-CF-06 → T-FI-03 → RT-IT-01
      (`evidence/video/storyline.md`). Measured 2026-10-09 on Claude (code e7b02a8): tasks
      23/24, red-team 26/26, 137 calls, US$1.17. Fail: T-CF-07 "above S$239,000" (R34).
      Chunk 6's duplicate risk IDs renumbered R34–R36.
      Whole-repo audit (2026-10-09) fixes: output guard strips Markdown images/links/web
      addresses + UI escapes `[` (R37, new RT-DE-07: red-team now **27** cases); `Id` only
      accepts plain tokens (R7). Fooled evidence re-exported (27/27). **Claude evidence is
      still the 26-case run from e7b02a8: re-run `export_evidence.py --llm claude` (~US$1.2)
      once the code is final, before the Oct 17 submission.**
- [x] 8. Extra metrics (2026-10-10). `analysis/health.py`: receivables/payables ageing with
      customer payment habits, cash trend, DSCR, break-even; `get_metrics` gains net working
      capital and supplier concentration. New viewer tools `get_ageing`, `get_cash_trend`,
      `get_health_ratios`. Uncategorised payments count as operating costs in DSCR/break-even
      (conservative). Generator records `receivables_ageing`, `payables_ageing`, `suppliers`;
      all values match ground truth exactly. cash_crunch: DSCR 1.46, break-even S$124,480.60/month,
      NWC S$180,484.34. Task suite now **28** cases (T-AN-06..09). Claude on the new 4: 3/4,
      US$0.08; T-AN-08 failed on a self-rounded "about S$8,200" (logged under R34).
- [x] 9. API backend (2026-10-10, brought forward by Daniel). FastAPI in `src/copilot/api/`
      (`api` extra): `/api/options`, `/api/session` (demo sign-in → HttpOnly SameSite=Strict
      cookie), `/api/dashboard` (8 panels via `agent.views.dashboard_panels`), `/api/chat`
      (`agent.handle`), `/api/clock/advance`. Role/business only from the session; bodies
      reject unknown fields. Caps: 20 sessions, 2 h idle, 40 Claude messages. Binds 127.0.0.1.
      Interim UI = `/docs`. 20 tests in `test_api.py`; isolation rule extended to `api/`.
      New risks R38 (frontend must use textContent) and R39 (spend caps).
**Build order decided 2026-10-10 (Daniel): features first, starting now, dashboard last:
11 → 12 → 13 → 14 → 10.** Docs, deck and video squeeze into the days before Oct 17
(the Oct 20 update window is the fallback). Streamlit stays the demo in the Oct 17 video.
Fintellect (Celia's app, `C:\Users\notse\Projects\Celia-Fintech-Hackathon-2026-main\`) is the
reference for 11–14 and 10: port ideas into Python with `Decimal`, never copy JS maths.
- [x] 11. Data foundation for accrual statements (2026-10-10; Daniel chose "4 + payroll + GST").
      New CSVs `opening_balances`, `inventory_snapshots`, `fixed_assets`, `loans`,
      `loan_schedule`, `payroll_runs` (optional, no warning if missing) + `gst` column on
      invoices/bills; schemas, adapter (natural-key duplicates, balance warning), 6 store tables.
      Generator: own RNG for the new data; **GST payments are now real quarterly returns**
      (output − input tax, input on supplier bills only, R40), so the 8 GST rows and cash_crunch's
      calibrated opening (S$125k → S$171k) changed; every other row is identical. Answer key
      `ground_truth["accrual"]`: opening BS, 12 months of P&L / BS / indirect cash flow, checks
      (BS difference 0.00 and closing cash = bank, asserted by the generator), GST returns, loan.
      Forecast now takes an ended quarter's GST from documents (S$9,867.75 on 29 Oct, not the
      S$16,055.60 pattern). **New key numbers (older figures above are pre-chunk-11):** cash
      S$156,526.85; forward low −S$17,816.17 (5 Nov, week 6); Dec need S$13,025.81; trade financing
      S$169.52 / 16.44%; DSCR 0.61 (was 1.46); NWC S$183,849.78; accrual net −S$22,467.49
      (cash_crunch), +S$73,321.67 (b2b). 17 new tests (`test_accrual_data.py`); fooled evidence
      re-exported (27/27). Not yet re-run on Claude.
- [x] 12. Accrual 3 statements (2026-10-11). `analysis/statements.py`: double entry rolled
      forward from the opening balance sheet, store data only; balances from real lines, cash =
      the bank. **Every P&L / balance-sheet / cash-flow line and both checks match
      `ground_truth["accrual"]` to the cent, all 12 months, both scenarios.** Daniel's choices:
      periods month / quarter / YTD / last 12; `get_metrics` keeps cash margins and adds an
      `accrual` block (no existing number changed); one viewer tool `get_financial_statements(
      period, month, statement)`; unmatched money gets its own line ("customer payments not yet
      matched", so prompt_injection balances with INV-1064's S$8,005.63 shown there). Uncategorised
      payments count as "other" costs. `GET /api/statements`. prompt_injection poisons a fixed-asset
      name + the lender (R41, RT-PI-08: red-team **28**); tasks **31** (T-AN-10..12). cash_crunch:
      Sep net −S$4,105.30 (op. margin −2.7% vs +34.7% cash), 12-month net −S$22,467.49, current
      ratio 2.06, loan due within 12 months S$46,610.93. b2b 12-month net +S$73,321.67. Limits R42.
      Fooled evidence re-exported (28/28). Claude on T-AN-10..12: 1/3 at first (correct
      answers, but my tests demanded the operating margin the questions didn't ask for, and
      margins came out as raw fractions); now either margin counts (Daniel) and the tool text
      says to show percentages → 3/3, ~US$0.14 total.
- [x] 13. Editing (2026-10-11): recorded adjustments + saved forecast assumptions, kept beside
      the imported data (tables `adjustments`, `forecast_assumptions`; undo = status change).
      Daniel's choices: kinds **accrued cost** (reverses next month), **relabel a payment**
      (to a cost line or owner drawings), **stock count**; staff `draft_adjustment`, owner
      `apply_adjustment` / `undo_adjustment` with the code; **last 3 complete months** only;
      assumptions **payment delay** + **recurring cost change**, owner `save_assumption` /
      `remove_assumption` with the code; viewer `list_adjustments`. Every adjustment is
      non-cash, one pair of lines: both checks stay 0.00 every month; `view=as_imported` equals
      the answer key exactly. Statements carry `adjustments` (net profit both ways); forecast
      carries `saved_assumptions` + `low_point_without_saved`; cash-basis figures unchanged (R44).
      Guards: accrual > 0, receipts and bill payments can't be relabelled, S$250k each, 20
      applied. cash_crunch: S$2,000 Sep accrual → Sep net −S$6,105.30; t00158 → owner drawings
      → Jul +S$307.50; "Bayfront pays 43 days" = what-if 3 weeks late (−S$70,660.41, 14 Nov).
      `GET /api/adjustments`, `/api/statements?view=`. Tasks **37** (T-ED-01..06, capability
      `editing`, grader `plus`), red-team **32** (RT-PI-09..11 via a poisoned t00158 memo in
      prompt_injection, RT-PE-06). Risks R43–R45. **No existing number changed.** Fooled evidence
      re-exported (32/32). Claude on the 10 new cases: tasks 6/6, red-team 4/4, ~US$0.5 (T-ED-02
      first failed: "relabel it" without "and apply it" made Claude draft and ask first;
      wording aligned with the other cases, Daniel 2026-10-11).
- [ ] 14. Worst/Expected/Best scenarios + 3-year financial model + break-even + valuation
      (DCF + EBITDA multiple, clearly labelled as an estimate). ~1 day.
- [ ] 10. Web dashboard: no-build HTML/JS served by the API; Streamlit stays as the fallback.
      **Design source (decided 2026-10-10): Celia's "Fintellect" app** (Node, kept outside this
      repo): reuse its look (`public/styles.css` tokens incl. dark mode, sidebar layout, KPI
      tiles, SVG charts, page structure), NOT its engine, server, sign-in or bakery dataset (her
      own synthetic data, not official). Every number comes from `/api`; the browser never
      calculates (her app.js does: don't copy that). Her `innerHTML` + `esc()` pattern must pass
      an R38 test on prompt_injection. Needs Celia's OK to license reused parts under MIT.
- [ ] Deferred (if time allows): extra adapters, deferred alert types, bank-detail
      verification, reconciliation, HF backend

### Deliverables
- [ ] Registration email sent (target Oct 10) and confirmation received
- [ ] Docs, deck and video drafting started (target ~Oct 12)
- [ ] 1. Technical documentation
- [ ] 2. Presentation deck (≤10 min)
- [ ] 3. Demo video (≤5 min)
- [ ] 4. Source code: README, GitHub link, deployment instructions, test cases
- [ ] 5. Security self-assessment report
- [ ] 6. Execution evidence: sandbox operation logs + demo video
- [ ] Early complete submission sent (target Oct 17)
