"""Execution evidence export (deliverable #6): suite runs written as readable operation logs.

Runs the task and/or red-team suites against the sandbox and writes, per mode:

    <out>/<mode>/index.md       run header, scorecards, one row per case, audit head hashes
    <out>/<mode>/run.json       everything, machine-readable
    <out>/<mode>/<suite>/<id>.md   one file per case

Modes: "claude" (tasks + red-team on the real model, the version we submit), "fooled"
(red-team with the scripted fooled model: the structure holds even if the model is fully
compromised) and "mock" (tasks on the rule-based assistant). fooled and mock need no API key.

Each case file shows the conversation turn by turn (tool calls with arguments and outcomes,
replies, system notices, the code-built confirmation prompt), every write attempt and policy
event from the audit log (allowed, blocked, pending, confirmed, executed, with role and
reason), the sandbox bank's operations, balances before and after, and the audit chain check
with its head hash for every business in that case's database. Publishing the head hashes
makes a later deletion of the newest audit rows detectable (known risk R26).

Redaction: everything written passes through `_Redactor`: "confirm 1234" becomes
"confirm ****" (any code, right or wrong), the session canary becomes [canary] and every
business's full account numbers are masked (••••1234). Tool arguments and audit parameters
are masked already (policy/audit.mask_value).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from copilot.agent.llm import LLM
from copilot.agent.mock_rules import RuleBasedLLM
from copilot.agent.state import Session
from copilot.evals import redteam, tasks
from copilot.evals.redteam import CaseRun
from copilot.policy.audit import mask_value
from copilot.runtime import ROOT, make_llm
from copilot.schemas import SGT, CopilotModel, mask, sgd

Mode = Literal["claude", "fooled", "mock"]
Suite = Literal["tasks", "redteam"]
SUITES: dict[Mode, tuple[Suite, ...]] = {
    "claude": ("tasks", "redteam"),
    "fooled": ("redteam",),
    "mock": ("tasks",),
}
# The demo video follows these cases, in this order (evidence/video/storyline.md).
STORYLINE: tuple[str, ...] = ("T-CF-01", "T-CF-06", "T-FI-03", "RT-IT-01")


# --- Evidence models ---------------------------------------------------------------------


class ToolStep(CopilotModel):
    tool: str
    args: Any
    outcome: str
    message: str
    data: Any = None


class TurnLog(CopilotModel):
    user: str
    assistant_notes: list[str] = []  # the model's words between tool calls
    steps: list[ToolStep] = []
    reply: str = ""
    notices: list[str] = []  # written by the system, not the model
    confirmation_prompt: str | None = None


class AuditRow(CopilotModel):
    seq: int
    sim_date: str
    user_id: str
    role: str
    tool: str
    kind: str
    params: Any
    outcome: str
    reason: str | None = None


class SandboxRow(CopilotModel):
    seq: int
    sim_date: str
    action: str
    object_id: str
    amount: str | None
    outcome: str
    reason: str | None = None


class BalanceRow(CopilotModel):
    account: str  # name and masked number
    before: str
    after: str
    change: str


class ChainRow(CopilotModel):
    business_id: str
    ok: bool
    entries: int
    head: str
    problem: str | None = None


class CaseEvidence(CopilotModel):
    suite: Suite
    id: str
    title: str
    about: str  # task: why the case matters; red-team: the attack
    defence: str | None = None
    scenario: str
    role: str
    model: str
    passed: bool
    skipped: bool = False
    failures: list[str] = []
    storyline: int | None = None  # position in the video storyline, 1-based
    turns: list[TurnLog] = []
    audit: list[AuditRow] = []  # write attempts and policy events (plain reads left out)
    reads: int = 0  # successful read calls, counted only
    sandbox: list[SandboxRow] = []
    balances: list[BalanceRow] = []
    chains: list[ChainRow] = []
    usage: dict[str, Any] | None = None  # Claude only: tokens and US$


class RunEvidence(CopilotModel):
    mode: Mode
    model: str
    effort: str | None
    generated_at: str
    commit: str
    scorecards: dict[str, str]
    usage: dict[str, Any] | None
    cases: list[CaseEvidence]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.cases)


# --- Running -----------------------------------------------------------------------------


def export(
    mode: Mode,
    out_dir: Path,
    case_ids: list[str] | None = None,
    effort: str = "",
    llm_factory: Callable[[], LLM] | None = None,
) -> RunEvidence:
    """Run the suites of `mode` and write the evidence under out_dir/mode.

    `llm_factory` overrides the model for the task suite and non-fooled red-team runs (tests).
    A case filter writes to out_dir/<mode>-partial, so it never replaces the full run's index.
    The target folder's case files are cleared first, so no stale case file survives.
    """
    if llm_factory is None:
        if mode == "claude":
            llm_factory = lambda: make_llm("claude", effort)  # noqa: E731
        else:
            llm_factory = RuleBasedLLM
    cases: list[CaseEvidence] = []
    scorecards: dict[str, str] = {}
    models: list[LLM] = []
    wanted = set(case_ids) if case_ids else None

    for suite in SUITES[mode]:
        module = tasks if suite == "tasks" else redteam
        selected = [c for c in module.load_cases() if wanted is None or c.id in wanted]
        if not selected:
            continue
        results = []
        for case in selected:
            if suite == "redteam" and mode == "fooled":
                run = redteam.run_case_session(case, None)
            else:
                llm = llm_factory()
                models.append(llm)
                run = module.run_case_session(case, llm)  # type: ignore[arg-type]
            results.append(run.result)
            cases.append(_case_evidence(suite, case, run))
        scorecards[suite] = module.scorecard(results)  # type: ignore[arg-type]

    claude = [m for m in models if hasattr(m, "usage")]
    evidence = RunEvidence(
        mode=mode,
        model=_model_name(mode, models),
        effort=getattr(claude[0], "effort", None) if claude else None,
        generated_at=datetime.now(SGT).isoformat(timespec="seconds"),
        commit=_commit(),
        scorecards=scorecards,
        usage=usage_total([m.usage for m in claude]) if claude else None,  # type: ignore[attr-defined]
        cases=cases,
    )
    write(evidence, folder_for(out_dir, mode, case_ids))
    return evidence


def folder_for(out_dir: Path, mode: Mode, case_ids: list[str] | None = None) -> Path:
    return out_dir / (f"{mode}-partial" if case_ids else mode)


def _model_name(mode: Mode, models: list[LLM]) -> str:
    names = sorted({getattr(m, "model", "") or m.name for m in models})
    if mode == "fooled":
        names = ["fooled model (scripted attack)", *names]
    return ", ".join(names)


def _commit() -> str:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "src", "tests", "data", "scripts"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except OSError:
        return "unknown"
    return f"{head or 'unknown'}{' + uncommitted changes' if dirty else ''}"


def usage_total(usages: list[Any]) -> dict[str, Any]:
    from copilot.agent.claude import Usage

    total = Usage()
    for u in usages:
        total.merge(u)
    return usage_dict(total)


def usage_line(u: dict[str, Any]) -> str:
    return (
        f"{u['calls']} calls, {u['input_tokens']:,} input + {u['cache_write_tokens']:,} "
        f"cache-write + {u['cache_read_tokens']:,} cache-read + {u['output_tokens']:,} output "
        f"tokens, about US${u['cost_usd']:.2f}"
    )


def usage_dict(u: Any) -> dict[str, Any]:
    return {
        "calls": u.calls,
        "input_tokens": u.input,
        "cache_write_tokens": u.cache_write,
        "cache_read_tokens": u.cache_read,
        "output_tokens": u.output,
        "cost_usd": round(u.cost_usd(), 4),
    }


# --- Building one case's evidence ----------------------------------------------------------


def _case_evidence(suite: Suite, case: Any, run: CaseRun) -> CaseEvidence:
    result = run.result
    fields: dict[str, Any] = {
        "suite": suite,
        "id": case.id,
        "title": case.title,
        "about": (case.why if suite == "tasks" else case.attack).strip(),
        "defence": None if suite == "tasks" else case.defence.strip(),
        "scenario": case.scenario,
        "role": case.role,
        "model": result.mode,
        "passed": result.passed,
        "skipped": getattr(result, "skipped", False),
        "failures": result.failures,
        "storyline": STORYLINE.index(case.id) + 1 if case.id in STORYLINE else None,
    }
    session = run.session
    if session is None:  # skipped before it ran
        return CaseEvidence.model_validate(fields)

    gw, biz = session.gateway, session.actor.business_id
    entries = gw.audit.entries(biz)
    after = gw.sandbox.balances(biz)
    fields["turns"] = _turns(session, run)
    fields["reads"] = sum(e.kind == "read" and e.outcome == "ok" for e in entries)
    fields["audit"] = [
        AuditRow(
            seq=e.seq,
            sim_date=e.sim_date.isoformat(),
            user_id=e.user_id,
            role=e.role.label,
            tool=e.tool,
            kind=e.kind,
            params=e.params,
            outcome=e.outcome,
            reason=e.reason,
        )
        for e in entries
        if not (e.kind == "read" and e.outcome == "ok")
    ]
    fields["sandbox"] = [
        SandboxRow(
            seq=ev.seq,
            sim_date=ev.sim_date.isoformat(),
            action=ev.action,
            object_id=ev.object_id,
            amount=None if ev.amount is None else str(ev.amount),
            outcome=ev.outcome,
            reason=ev.reason,
        )
        for ev in gw.sandbox.events(biz)
    ]
    fields["balances"] = [
        BalanceRow(
            account=f"{a.name} {mask(a.account_number)}",
            before=str(run.balances_before[a.id]),
            after=str(after[a.id]),
            change=str(after[a.id] - run.balances_before[a.id]),
        )
        for a in gw.store.list_accounts(biz)
        if a.id in run.balances_before and a.id in after
    ]
    businesses = gw.store.conn.execute("SELECT id FROM businesses ORDER BY rowid").fetchall()
    fields["chains"] = [
        ChainRow(business_id=b, **gw.audit.verify_chain(b).model_dump(exclude={"first_bad_seq"}))
        for (b,) in businesses
    ]
    if hasattr(session.llm, "usage"):
        fields["usage"] = usage_dict(session.llm.usage)  # type: ignore[attr-defined]
    evidence = CaseEvidence.model_validate(fields)
    return _Redactor(session).model(evidence)


def _turns(session: Session, run: CaseRun) -> list[TurnLog]:
    history = session.history
    bounds = [*run.marks[1:], len(history)]
    turns = []
    for start, end, reply in zip(run.marks, bounds, run.replies, strict=True):
        user = ""
        notes: list[str] = []
        steps: dict[str, dict[str, Any]] = {}  # by call id, in call order
        for m in history[start:end]:
            if m.role == "user" and not user:
                user = m.content  # the code is already hidden here (agent/loop._hide_code)
            elif m.role == "assistant":
                if m.content and m.tool_calls:
                    notes.append(m.content)
                for call in m.tool_calls:
                    steps[call.id] = {
                        "tool": call.name,
                        "args": mask_value(call.arguments),
                        "outcome": "",
                        "message": "",
                    }
            elif m.role == "tool" and m.tool_call_id in steps:
                payload = json.loads(m.content)
                steps[m.tool_call_id].update(
                    outcome=payload.get("outcome", ""),
                    message=payload.get("message", ""),
                    data=payload.get("data"),
                )
        turns.append(
            TurnLog(
                user=user,
                assistant_notes=notes,
                steps=[ToolStep.model_validate(s) for s in steps.values()],
                reply=reply.text,
                notices=list(reply.notices),
                confirmation_prompt=reply.pending_prompt,
            )
        )
    return turns


class _Redactor:
    """Last line of defence for everything written: codes, canary, full account numbers."""

    _CONFIRM = re.compile(r"(confirm\s*#?\s*)\d{4}\b", re.IGNORECASE)

    def __init__(self, session: Session) -> None:
        self.canary = session.canary
        numbers = redteam.secret_numbers(session)
        self.numbers = sorted(set(numbers), key=len, reverse=True)

    def text(self, value: str) -> str:
        out = self._CONFIRM.sub(r"\1****", value)
        out = out.replace(self.canary, "[canary]")
        for number in self.numbers:
            out = out.replace(number, mask(number))
        return out

    def value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {k: self.value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.value(v) for v in value]
        return value

    def model(self, evidence: CaseEvidence) -> CaseEvidence:
        return CaseEvidence.model_validate(self.value(evidence.model_dump(mode="json")))


# --- Writing -----------------------------------------------------------------------------


def write(run: RunEvidence, folder: Path) -> None:
    if folder.exists():
        for sub in SUITES[run.mode]:
            shutil.rmtree(folder / sub, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    for case in run.cases:
        path = folder / case.suite / f"{case.id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_case(case, run), encoding="utf-8", newline="\n")
    (folder / "index.md").write_text(render_index(run), encoding="utf-8", newline="\n")
    (folder / "run.json").write_text(
        json.dumps(run.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _esc(text: str) -> str:
    """Plain text for Markdown: tags (e.g. <untrusted>) stay visible instead of vanishing."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _cell(value: Any) -> str:
    if value is None or value == "":
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return _esc(text).replace("|", "\\|").replace("\n", "<br>")


_PLAIN_TAG = re.compile(r"</?untrusted>")
_FLAGGED_TAG = re.compile(r"<untrusted flagged=\"[^\"]*\">")


def _unwrap(text: str) -> str:
    """Readable form of a tool message: the model saw the <untrusted> labels (kept as-is in the
    data blocks); here plain labels are dropped and flagged ones are marked."""
    return _PLAIN_TAG.sub("", _FLAGGED_TAG.sub("⚠ flagged as instruction-like: ", text))


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in _esc(text).splitlines())


def _status(case: CaseEvidence) -> str:
    return "SKIP" if case.skipped else ("PASS" if case.passed else "FAIL")


def _writes(case: CaseEvidence) -> str:
    by_tool: dict[str, list[str]] = {}
    for row in case.audit:
        if row.kind == "write":
            by_tool.setdefault(row.tool, []).append(row.outcome)
    return "; ".join(f"{t}: {' → '.join(o)}" for t, o in by_tool.items()) or "none"


def render_index(run: RunEvidence) -> str:
    lines = [
        f"# Execution evidence: {run.mode} run",
        "",
        "Sandbox operation logs for deliverable #6 (Topic E, Fintellect). Every case "
        "below ran in a fresh simulated bank; each case file shows the conversation, every "
        "write attempt and its outcome, the sandbox operations and balances, and the audit "
        "hash-chain check.",
        "",
        "| | |",
        "|---|---|",
        f"| Model | {_cell(run.model)} |",
    ]
    if run.effort:
        lines.append(f"| Effort | {run.effort} |")
    lines += [
        f"| Generated | {run.generated_at} (SGT) |",
        f"| Code version | `{run.commit}` |",
        f"| Result | {sum(c.passed for c in run.cases if not c.skipped)}/"
        f"{sum(not c.skipped for c in run.cases)} passed"
        + (
            f", {sum(c.skipped for c in run.cases)} skipped"
            if any(c.skipped for c in run.cases)
            else ""
        )
        + " |",
    ]
    if run.usage:
        lines.append(f"| Claude usage | {usage_line(run.usage)} |")
    lines += [
        "",
        "Sensitive values are masked: account numbers show only the last 4 digits, "
        "confirmation codes appear as `****` and the system prompt's canary as `[canary]`.",
        "",
    ]
    for suite, card in run.scorecards.items():
        title = "Task suite" if suite == "tasks" else "Red-team suite"
        lines += [f"## {title} scorecard", "", "```", card, "```", ""]

    lines += [
        "## Cases",
        "",
        "★ = in the demo video storyline (see `evidence/video/storyline.md`).",
        "",
        "| | Case | Title | Result | Write attempts | Audit chain | Head hash |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in run.cases:
        own = c.chains[0] if c.chains else None
        chain = "" if not c.chains else ("verified" if all(x.ok for x in c.chains) else "BROKEN")
        star = f"★{c.storyline}" if c.storyline else ""
        lines.append(
            f"| {star} | [{c.id}]({c.suite}/{c.id}.md) | {_cell(c.title)} | {_status(c)} | "
            f"{_cell(_writes(c))} | {chain} | {f'`{own.head[:16]}…`' if own else ''} |"
        )
    lines += [
        "",
        "Head hash: the SHA-256 of the newest audit row of the case's main business (full "
        "value and every other business in the case file). The audit log is a hash chain, so "
        "editing, deleting or reordering any row, or deleting the newest rows, no longer "
        "matches these published values.",
        "",
    ]
    return "\n".join(lines)


def render_case(case: CaseEvidence, run: RunEvidence) -> str:
    lines = [
        f"# {case.id}: {_esc(case.title)}",
        "",
        f"**Result: {_status(case)}**  ·  suite: {case.suite}  ·  scenario: `{case.scenario}`  ·  "
        f"signed-in role: **{case.role}**  ·  model: {_esc(case.model)}",
        "",
    ]
    if case.storyline:
        lines += [f"★ Demo video storyline, step {case.storyline} of {len(STORYLINE)}.", ""]
    if case.suite == "tasks":
        lines += [f"**Why this case:** {_esc(case.about)}", ""]
    else:
        lines += [
            f"**Attack:** {_esc(case.about)}",
            "",
            f"**Defence:** {_esc(case.defence or '')}",
            "",
        ]
    if case.failures:
        label = "Skipped" if case.skipped else "Failures"
        lines += [f"**{label}:**", ""] + [f"- {_esc(f)}" for f in case.failures] + [""]
    if case.skipped:
        return "\n".join(lines)

    lines += ["## Conversation", ""]
    for n, turn in enumerate(case.turns, 1):
        lines += [f"### Turn {n}", "", "**User:**", "", _quote(turn.user), ""]
        for note in turn.assistant_notes:
            lines += ["*Assistant (before calling tools):*", "", _quote(note), ""]
        if turn.steps:
            lines += ["| Tool call | Arguments | Outcome | Message |", "|---|---|---|---|"]
            lines += [
                f"| `{s.tool}` | {_cell(s.args or '')} | **{s.outcome}** | "
                f"{_cell(_unwrap(s.message))} |"
                for s in turn.steps
            ]
            lines.append("")
            data = [s for s in turn.steps if s.data not in (None, {}, [])]
            if data:
                lines += ["<details><summary>Tool result data</summary>", ""]
                for s in data:
                    body = json.dumps(s.data, indent=2, ensure_ascii=False)
                    lines += [f"`{s.tool}`", "", "```json", body, "```", ""]
                lines += ["</details>", ""]
        if turn.reply:
            lines += ["**Assistant:**", "", _quote(turn.reply), ""]
        for notice in turn.notices:
            lines += ["**System notice** (written by code, not the model):", "", _quote(notice), ""]
        if turn.confirmation_prompt:
            lines += [
                "**Confirmation prompt** (written by code, shown to the user):",
                "",
                _quote(turn.confirmation_prompt),
                "",
            ]

    lines += [
        "## Write attempts and policy events (audit log)",
        "",
        f"Successful read-only tool calls are counted, not listed: {case.reads}.",
        "",
    ]
    if case.audit:
        lines += [
            "| Seq | Sim date | User | Role | Tool | Kind | Parameters | Outcome | Reason |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {r.seq} | {r.sim_date} | {_cell(r.user_id)} | {r.role} | `{r.tool}` | {r.kind} | "
            f"{_cell(r.params)} | **{r.outcome}** | {_cell(r.reason)} |"
            for r in case.audit
        ]
    else:
        lines.append("None: no write was attempted.")
    lines.append("")

    lines += ["## Sandbox bank operations", ""]
    if case.sandbox:
        lines += [
            "| Seq | Sim date | Action | Object | Amount (S$) | Outcome | Reason |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {r.seq} | {r.sim_date} | {r.action} | {_cell(r.object_id)} | {r.amount or ''} | "
            f"**{r.outcome}** | {_cell(r.reason)} |"
            for r in case.sandbox
        ]
    else:
        lines.append("None: the sandbox bank was not asked to move or record any money.")
    lines += [
        "",
        "**Balances:**",
        "",
        "| Account | Before | After | Change |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {_cell(b.account)} | {sgd(b.before)} | {sgd(b.after)} | {sgd(b.change)} |"
        for b in case.balances
    ]
    lines += [
        "",
        "## Audit hash chain",
        "",
        "| Business | Verified | Entries | Head hash |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {c.business_id} | {'yes' if c.ok else 'NO: ' + _cell(c.problem)} | {c.entries} | "
        f"`{c.head}` |"
        for c in case.chains
    ]
    if case.usage:
        u = case.usage
        lines += [
            "",
            f"Claude usage for this case: {u['calls']} calls, about US${u['cost_usd']:.3f}.",
        ]
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "STORYLINE",
    "SUITES",
    "CaseEvidence",
    "RunEvidence",
    "export",
    "folder_for",
    "usage_line",
    "usage_total",
]
