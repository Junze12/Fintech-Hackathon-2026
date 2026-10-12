# Execution evidence (deliverable #6)

Sandbox operation logs from running the task suite (24 scripted business tasks) and the
red-team suite (27 attacks; the committed Claude run predates RT-DE-07 and has 26) against
the simulated bank. Readable without running any code:
start at an `index.md`.

| Folder | What ran | In git |
|---|---|---|
| `logs/claude/` | Both suites with Claude Sonnet 5.5 deciding for itself. **The submitted run.** | yes |
| `logs/fooled/` | Red-team suite with a scripted model that falls for every attack: shows the code-level defences hold even if the model is fully compromised. | yes |
| `logs/mock/` | Task suite on the rule-based assistant (offline). | no, regenerate |

Each case file has five parts:
1. **Conversation:** every user message, each tool the assistant called (arguments,
   outcome, message), the assistant's reply, and anything the *system* told the user
   (confirmation prompts and payment results are written by code, not by the model).
2. **Write attempts and policy events:** every row of the audit log except plain reads:
   proposed (`pending`), `confirmed`, `executed`, `blocked`, `denied`, `flagged`, with the
   signed-in user, their role and the reason.
3. **Sandbox bank operations:** what the simulated bank actually did, with amounts.
4. **Balances** of each account before and after the case.
5. **Audit hash chain:** whether the chain verifies, and its head hash. Each audit row
   holds the hash of the row before it, so editing, deleting or reordering a row breaks the
   chain; publishing the head hash here also makes deleting the newest rows detectable.

Masking: account numbers show only their last 4 digits, confirmation codes appear as
`confirm ****`, and the system prompt's secret marker (canary) as `[canary]`. The export
applies this to everything it writes, and `tests/unit/test_evidence.py` checks it.

Regenerate:
```
python scripts/export_evidence.py                 # fooled + mock, offline, no API key
python scripts/export_evidence.py --llm claude    # the submitted run, about US$1.65
```
A run limited with `--case` is written to `logs/<mode>-partial/` (not in git), so it never
replaces a full run.

The demo video (`video/storyline.md`) follows four of these cases.
