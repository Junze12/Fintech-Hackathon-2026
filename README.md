# Fintellect

*Our entry for Topic E (SME Finance Copilot), 2026 Shenzhen International FinTech Competition,
International Track.*

Fintellect is an AI finance assistant for Singapore small businesses. It reads the books,
warns before cash runs short, compares ways to close the gap (collecting, rescheduling,
financing with full costs), and carries out actions such as paying a bill, but only after the
owner types a confirmation code. Everything runs on a simulated bank, so no real money moves.

The AI (Claude Sonnet 5.5) chooses what to do and explains it. **Every number comes from
tested code, and every action is checked by code**, so the protections hold even if the AI is
fooled.

## For judges: three ways to see it

**1. See Claude at work without running anything.** `evidence/logs/claude/index.md` lists
every test case run on Claude (date, code version, cost, pass/fail). Each case file shows the
conversation, every tool call and action with its outcome, the bank balances before and after,
and the audit-log check. The demo video follows the same scenarios (`evidence/video/`).

**2. Run the dashboard offline, no API key needed** (Python 3.11+, about 2 minutes):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[api]"
python -m copilot.api            # then open http://127.0.0.1:8000/
```

Pick a sample business, sign in as **Owner**, and choose the **Rule-based demo** assistant.
Every page works offline, and the assistant handles the suggested questions, payments ("Pay
bill BL-5048", then type the code it shows) and reminders. It follows fixed phrases; option 1
shows the real AI's reasoning and wording.

**3. Run it with Claude, using your own key** (optional): `python -m pip install -e ".[api,llm]"`,
put `ANTHROPIC_API_KEY=sk-ant-...` in a file named `.env` in the repo root, restart, and choose
**Claude** at sign-in. A question costs a few US cents; each session is capped at 40 messages.
The Anthropic API is not available in every region (including mainland China); options 1 and 2
work anywhere.

## Using the dashboard

| Page | What it shows |
|---|---|
| Overview | Cash today, the 13-week forecast with its likely range, key measures, how customers pay, alerts |
| Cash plan | The chance cash lasts, where the gap comes from, every plan compared, financing options |
| Outlook | Worst / Expected / Best over 3 years, break-even, an estimated value |
| Statements | Profit and loss, balance sheet and cash flow (downloadable as Excel) |
| Books check | Bookkeeping errors, unpaid invoices and bills by age, recorded corrections |
| Glossary | Every term in plain words (also on the (i) icons) |

The assistant sits on every page. "Advance 7 days" moves the simulated clock: customers pay,
bills go out and alerts update. A simpler chat-only fallback: `python -m pip install -e ".[ui]"`
then `streamlit run src/copilot/ui/app.py`.

**Your own data:** choose "Your own data" at sign-in and pick your CSV files. Only
`business.csv` is required; the page lists what each other file adds and offers empty
templates. Limits: 2 MB per file, 5 MB in total. The data stays in memory for that session
only. Working example: `data/samples/demo_business/`.

**Sample businesses** (all synthetic): Straits Harbour Distribution (heading for a cash
shortfall), Clearpath Systems (healthy, one dominant customer), Straits Harbour with poisoned
data (attack demo), and Straits Harbour with messy books (ten planted bookkeeping errors).

## Tests

```bash
python -m pip install -e ".[dev,api]"
pytest                                                   # 1,000+ tests, offline, about 2.5 min
python scripts/run_eval.py --suite tasks                 # 57 task cases, offline assistant
python scripts/run_eval.py --suite redteam               # 37 attack cases, "fooled" model
python scripts/run_eval.py --suite redteam --llm claude  # attack cases on Claude (needs a key)
python scripts/export_evidence.py --llm claude           # re-create evidence/logs/claude (about US$3.3)
```

- **Task cases** (`tests/tasks/`): readable conversations with the tools and values the answer
  must contain. Every S$ amount and percentage in a reply must come from a tool result.
- **Attack cases** (`tests/redteam/`): induced transfers, data extraction, privilege escalation
  and prompt injection; each states the attack and the expected safe outcome.

## Documentation

| Document | Contents |
|---|---|
| `docs/technical/architecture.md` | System design and security design |
| `docs/technical/algorithms.md` | How every number is calculated |
| `docs/security/self-assessment.md` | Permission tiers, defences, attack results, known risks |
| `evidence/` | Execution logs and the demo video storyline |

## Project layout

```
src/copilot/adapters/    CSV import            src/copilot/policy/   roles, rules, confirmation, audit
src/copilot/sandbox/     simulated bank        src/copilot/tools/    what the AI can call
src/copilot/analysis/    financial analysis    src/copilot/agent/    AI conversation loop
src/copilot/cashflow/    forecast and plans    src/copilot/api/      web server and dashboard
src/copilot/financing/   financing matching    src/copilot/evals/    test runners, evidence export
data/                    synthetic businesses and the financing catalogue
```

## Data and licences

All data is synthetic; no real personal or business data is used. The financing catalogue
(`data/catalogue/products.json`) lists fictional lenders with illustrative terms, not offers.

This project is MIT-licensed (`LICENSE`). Third-party components:

| Component | Use | Licence |
|---|---|---|
| pydantic | data models and validation | MIT |
| fastapi, starlette, uvicorn | web server (`api` extra) | MIT, BSD-3-Clause, BSD-3-Clause |
| openpyxl, et-xmlfile | Excel downloads (`api` extra) | MIT |
| anthropic, python-dotenv | Claude API client, reads `.env` (`llm` extra) | MIT, BSD-3-Clause |
| streamlit | fallback chat UI (`ui` extra) | Apache-2.0 |
| pytest, ruff, PyYAML, httpx, hatchling | tests and build (development only) | MIT, MIT, MIT, BSD-3-Clause, MIT |

The dashboard uses no third-party front-end code, fonts or CDNs.
Claude Sonnet 5.5 is used as a service through the Anthropic API under Anthropic's commercial
terms; no model weights are included.
