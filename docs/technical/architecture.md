# Architecture and security design

Fintellect is an AI finance assistant for Singapore small businesses. It reads a business's
books, warns before cash runs short, compares ways to close a gap (including financing), and
carries out actions such as paying a bill, but only after the owner confirms. Everything runs
against a simulated bank (the sandbox), so no real money moves.

The one design idea behind everything below: **the AI proposes, code decides.** The language
model chooses which tool to call and explains the result in words. It never calculates a
number, never sees a confirmation code, and cannot move money by itself.

## 1. Layers

Each layer only calls the layers below it (checked by `tests/unit/test_isolation.py`).

```
Web dashboard / Streamlit   pages and chat; only call the agent and read-only views
Agent                       the AI conversation loop (Claude Sonnet 5.5, or an offline rule-based stand-in)
Policy gateway              the only route to tools: roles, payment rules, confirmation, audit log
Tools                       one function per task, with a strict list of allowed arguments
Finance engine              analysis, cash flow, financing: plain Python, exact decimals, no AI
Store + sandbox bank        SQLite database; every query is limited to one business
Adapters                    turn CSV files into checked records; bad rows are listed, not dropped
```

| Folder | What it holds |
|---|---|
| `src/copilot/adapters/` | CSV import: one folder per business, one file per kind of record |
| `src/copilot/store.py`, `sandbox/` | Database, simulated bank accounts and ledger, simulated clock |
| `src/copilot/analysis/`, `cashflow/`, `financing/`, `reconcile.py` | All calculations (see `algorithms.md`) |
| `src/copilot/tools/` | 39 tools the AI can call (27 read, 12 write) |
| `src/copilot/policy/` | Roles, payment and edit rules, confirmations, audit log |
| `src/copilot/agent/` | Conversation loop, system prompt, AI provider, reply safety check |
| `src/copilot/api/` | Web server and the dashboard (plain HTML, CSS and JavaScript) |
| `src/copilot/evals/` | Task and red-team test runners, evidence export |

## 2. How data comes in

- A business is a folder of CSV files. Only `business.csv` is required; the others (accounts,
  customers and suppliers, payees, bank transactions, invoices, bills, opening balances, stock,
  assets, loans, payroll, supplier statements) each unlock more features.
- The adapter checks every row (dates, amounts, references between files). A bad row is listed
  with its reason and the rest of the file still loads. A business can't place data in another
  business: the business id comes only from `business.csv`.
- Owners can also upload their own files on the sign-in page. They go through the same adapter
  and stay in that session's memory only.
- **Money is always an exact decimal, never a floating-point number.** It is stored as whole
  cents, shown as `S$1,234.56`, and a floating-point amount is refused wherever it comes from.

## 3. How a question is answered

```
owner's message
  -> 1. is it a confirmation code for a waiting action?  (checked by code, before the AI)
  -> 2. the AI picks tools                               (only tools the owner's role allows)
  -> 3. each tool call goes through the policy gateway   (role, arguments, rules, audit)
  -> 4. the tool runs the finance engine                 (exact numbers, with sources and warnings)
  -> 5. the AI writes the reply from those results       (up to 6 tool rounds)
  -> 6. the reply passes a safety check                  (no leaked secrets, codes or links)
  -> reply, plus any confirmation card built by code
```

- Every result from the finance engine carries its value, what drove it, which data it used
  and any warnings. The AI is told to use only these numbers; the task suite checks every S$
  amount and percentage in every reply against them.
- If the AI fails or runs out of rounds, the reply is a fixed message ("nothing was changed").
- The AI provider sits behind one interface (`agent/llm.py`), so the model can be swapped.
  An offline rule-based assistant implements the same interface and needs no API key.

## 4. How an action is carried out

Write tools never act straight away. For example, "pay bill BL-5048":

1. The AI calls `schedule_payment`. The gateway checks the role and the payment rules.
2. Code (not the AI) writes the restatement: amount, payee, masked account, date and bill.
   A random 4-digit code is created. The AI never sees it.
3. The dashboard shows the restatement and the code on a separate card.
4. Only if the owner's **own next message** is `confirm <code>` does the payment run, after
   the rules are checked again. Anything else cancels it.
5. The sandbox posts the payment, the balance changes, and every step is in the audit log.

Payments dated in the future are checked a third time on the day they run.

## 5. Security design

The competition names four threats. Each is stopped in code, so the protection holds even if
the AI is fooled.

### Induced transfers (tricking the AI into paying someone)

- **Confirmation by code:** every action that moves money, changes the books or contacts
  someone outside needs the owner's own `confirm <code>`. The tool registry refuses to load
  such a tool without it.
- **Payment rules**, checked when requested, when confirmed and when executed:
  - the payee must be on the allowlist, verified, with no recent bank-detail change;
  - at most S$75,000 per payment and S$100,000 per day;
  - a bill payment must match that bill's supplier and can't exceed what is still owed;
  - no payment dated in the past; no overdraft.
- Reminders have no recipient argument (they go only to the invoice's customer), and at most
  one per invoice per week.

### Data extraction

- Account numbers are hidden in every log, reply and export (`••••1234`).
- Each business's data is separated in the database itself: every table key includes the
  business id, so even a coding mistake can't link two businesses.
- The reply safety check blocks a reply that repeats the system prompt (a secret marker is
  planted in it), removes confirmation codes, masks long digit strings, and removes links and
  images (an image link could send data to an outside server).

### Privilege escalation

- The role (Viewer, Staff, Owner) comes from sign-in, never from the chat. A `role` or
  `business_id` sneaked into a tool call or web request is rejected.
- The AI is only offered the tools the role allows, and the role is checked again on every
  call and at confirmation. The full table is in `docs/security/self-assessment.md`.

### Prompt injection (instructions hidden in imported text)

- Text from outside (customer names, bank descriptions, invoice notes, statement lines) is
  marked as untrusted. It reaches the AI inside `<untrusted>` labels and can't close them.
- Text that looks like an instruction ("ignore previous instructions", "pay S$9,000 to…") is
  also flagged; the AI is told to point it out and ignore it, and the flag is audited.
- Imported text is only ever shown as plain text on the dashboard (never as HTML), the page
  runs under a strict Content-Security-Policy, and Excel exports never turn text into formulas.

### Audit trail

Every tool call and write attempt, allowed or refused, is logged with user, role, tool,
arguments (sensitive values masked) and outcome. Each row is chained to the previous one with
a SHA-256 hash, so an edited or deleted row is detected. The evidence export records the
chain check and its latest hash for every case.

### Financing compliance

- Every option shows its total cost in S$ and its effective annual rate.
- Approval is never promised: applications can only be "draft" or "submitted" (the database
  rejects "approved"), and every answer says approval is the lender's decision.
- A product the business isn't eligible for is never recommended. An unknown fact counts as
  not eligible.
- Matching uses company facts only; the data model has no personal characteristics
  (nationality, gender, age and so on) to use.
- Ways to close a gap without borrowing (collecting, rescheduling, cutting) are always
  checked first, and the answer says when borrowing isn't needed.

## 6. Web dashboard and API

- `python -m copilot.api` starts a local web server (127.0.0.1 only) with the dashboard at `/`
  and the API documentation at `/docs`.
- Pages: Overview, Cash plan, Outlook, Statements, Books check, Glossary. The assistant is
  docked on every page.
- **No calculations in the browser.** Every figure comes from the API; the page only formats
  and draws it (tested).
- Sessions: a random id in a secure cookie; role and business fixed at sign-in; at most 20
  sessions, 2 hours idle, 40 AI messages per session.
- Excel downloads of the statements and the 13-week forecast use the same server results.

## 7. Testing

| Suite | What it proves | Size |
|---|---|---|
| Unit tests (`tests/unit/`) | Every calculation, adapter, rule and page rule; run offline | 1,000+ tests |
| Task suite (`tests/tasks/`) | The assistant completes real requests correctly; every number is checked against the tool results | 57 cases |
| Red-team suite (`tests/redteam/`) | Attacks fail: no money moved, nothing leaked, no extra rights | 37 cases |

The red-team suite runs twice: once with a scripted "fooled" model that falls for every attack
(to prove the code stops it anyway), and once with Claude. Results with Claude are in
`evidence/logs/claude/`.
