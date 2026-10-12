# SME Finance Copilot

An AI agent for Singapore small-business owners: business financial analysis, cash-flow
management and alerts, and financing-option matching. It proposes actions and carries them
out in a simulated bank sandbox only after explicit user confirmation.

Entry for the 2026 Shenzhen International FinTech Competition, International Track, Topic E.

> Status: early development. See `CLAUDE.md` → Status for progress.

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
```

### Connect the AI model (Claude)

The assistant runs on Claude Sonnet 5.5 through the Anthropic API. Each person running it uses
their own API key (console.anthropic.com -> API Keys). We recommend setting a monthly spend
cap in the Console.

```bash
python -m pip install -e ".[llm]"
```

Create a file named `.env` in the repo root (it is gitignored, so it never reaches GitHub):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Optional settings in the same file: `COPILOT_MODEL` (default `claude-sonnet-5-5`) and
`COPILOT_EFFORT` (default `medium`). Without a key, everything still runs on the built-in
rule-based assistant, offline.

## Run the demo

```bash
python -m pip install -e ".[ui]"
streamlit run src/copilot/ui/app.py
```

Pick a sample business, a demo user (Owner, Staff or Viewer) and the assistant (Claude, or the
rule-based demo that needs no key) in the sidebar. Each session starts from a fresh simulated
sandbox. Try "How much cash do we have?",
"Any alerts?", "Pay bill BL-5048" (then reply with the code shown) or "Remind INV-1057".
The "poisoned data (red-team)" business has attacks hidden in its imported text: try
"Any unmatched receipts?" to see one shown as data and flagged, then "Mark INV-1064 paid".

## Run the API (for the web dashboard)

```bash
python -m pip install -e ".[api]"
python -m copilot.api            # http://127.0.0.1:8000/docs
```

A JSON API over the same agent, panels and simulated clock as the Streamlit app, for the web
dashboard (chunk 10). `/docs` is an interactive page: sign in with `POST /api/session`
(`{"scenario": "cash_crunch", "role": "owner"}`), then try `GET /api/dashboard`,
`POST /api/chat` (`{"message": "Pay bill BL-5048"}`, then `{"message": "confirm <code>"}`) and
`POST /api/clock/advance` (`{"days": 7}`). It listens on this machine only. The demo sign-in has
no password (known risk R11), so don't expose it to a network; `COPILOT_API_ROLES=staff,viewer`
hides the Owner role. Claude sessions are capped at 40 messages and 20 live sessions.

## Run the checks

```bash
ruff check .
ruff format --check .
pytest                       # offline: never calls the API, even when a key is set
RUN_LIVE=1 pytest -m live    # optional: one real Claude call (about a cent)
```

## Run the red-team suite

```bash
python scripts/run_eval.py --suite redteam              # scripted "fooled" model
python scripts/run_eval.py --suite redteam --llm mock   # rule-based assistant
python scripts/run_eval.py --suite redteam --llm claude # real model (about US$1, cost printed)
```

Each case in `tests/redteam/` is a readable YAML file: the attack, the defence that should
stop it, the conversation, what a model that fell for it would do, and the expected safe
outcome. The script prints a pass/fail scorecard by threat (induced transfers, data
extraction, privilege escalation, prompt injection). `pytest` runs the same cases.

## Run the task suite

```bash
python scripts/run_eval.py --suite tasks                              # rule-based assistant
python scripts/run_eval.py --suite tasks --llm claude                 # real model (about US$0.65)
python scripts/run_eval.py --suite tasks --llm claude --effort low    # compare effort levels
```

Each case in `tests/tasks/` is a readable YAML conversation on one of the synthetic businesses:
what the user says, which tools must be called, and the values the answer must show, taken from
`data/synthetic/*/ground_truth.json`. Every S$ amount and percentage in a reply must also come
from a tool result, so a number the model invents or works out itself fails the case. Cases the
rule-based assistant can't handle are skipped for it, with the reason; `pytest` runs the rest.

## Export the execution evidence

```
python scripts/export_evidence.py                 # fooled red-team + mock tasks, offline
python scripts/export_evidence.py --llm claude    # both suites on Claude (about US$1.65)
```

Writes readable logs to `evidence/logs/<mode>/` (start at `index.md`): each case's
conversation, tool calls, write attempts with role and outcome, sandbox bank operations,
balances, and the audit hash-chain check. Account numbers, confirmation codes and the canary
are masked. See `evidence/README.md`.

## Project layout

- `src/copilot/schemas.py`: shared data models (the contract every layer uses)
- `src/copilot/*/`: one package per layer (adapters, sandbox, analysis, cashflow, financing,
  policy, tools, agent, ui, api)
- `src/copilot/runtime.py`: wires the layers into a demo session
- `src/copilot/evals/`: the red-team and task-suite runners
- `tests/unit/`: unit and end-to-end tests (the Streamlit test runs when the `ui` extra is installed)
- `tests/redteam/`: attack cases (YAML) and their pytest runner
- `tests/tasks/`: task cases (YAML) scored against ground truth, and their pytest runner
- `docs/technical/`: architecture and security design notes
- `evidence/`: exported sandbox operation logs (deliverable #6) and the demo video storyline

## Data

All data in this repo is synthetic. No real personal or business financial data is used.
The financing catalogue (`data/catalogue/products.json`) is our own illustrative data:
fictional lenders with plausible terms modelled on Singapore SME financing types. It is not
an offer from any real lender.

## Licence

MIT, see `LICENSE`.

### Third-party components

| Component | Use | Licence |
|---|---|---|
| pydantic | data models and validation | MIT |
| pytest | tests (dev only) | MIT |
| ruff | lint and format (dev only) | MIT |
| PyYAML | red-team case files (dev only) | MIT |
| hatchling | build backend | MIT |
| streamlit | demo chat UI (optional `ui` extra) | Apache-2.0 |
| anthropic | Claude API client (optional `llm` extra) | MIT |
| fastapi | JSON API (optional `api` extra) | MIT |
| starlette | web framework under FastAPI (optional `api` extra) | BSD-3-Clause |
| uvicorn | API server (optional `api` extra) | BSD-3-Clause |
| httpx | API test client (dev only) | BSD-3-Clause |
| python-dotenv | reads `.env` (optional `llm` extra) | BSD-3-Clause |

The AI model (Claude Sonnet 5.5) is used as a service through the Anthropic API under
Anthropic's commercial terms; no model weights are distributed with this repo.
