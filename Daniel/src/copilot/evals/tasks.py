"""Task suite runner: scripted conversations (tests/tasks/*.yaml) scored against ground truth.

Each case is a short conversation on a synthetic business. Per user turn it lists what a
correct assistant does: the tools it must (or must not) call, the values its answer must
contain, phrases for answers that are words rather than numbers (no data, no loan needed) and,
for clarification, that it asks a question. Expected values come from the scenario's
ground_truth.json wherever the truth is known; forecast-type values come from the tool result
and are checked against the truth within its tolerance.

Values are matched in the reply allowing for display rounding: "S$153.2k" matches 153,161.41
(the reply claims a precision of S$50), "16.4%" matches an EIR of 16.44. Signs are ignored
("-S$13,260.76" and "S$13,260.76 short" both match).

Universal check, every turn, every case (CLAUDE.md rules 1 and 7): every S$ amount and
percentage in the assistant's words must trace to a number in this session's tool results or
the user's own messages, within the same rounding. A number the model worked out or invented
fails the case.

Models: the rule-based mock (offline, what pytest runs; cases it can't handle carry
`mock_skip` with the reason) or any other LLM, e.g. Claude via scripts/run_eval.py.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from copilot.agent import handle
from copilot.agent.llm import LLM
from copilot.agent.mock_rules import RuleBasedLLM
from copilot.agent.state import AgentReply, Session
from copilot.evals.redteam import _EFFECT_OUTCOMES, SCENARIOS_DIR, CaseRun, _user_text
from copilot.policy.audit import AuditOutcome
from copilot.runtime import ROOT, open_scenario
from copilot.schemas import CopilotModel, Role

CASES_DIR = ROOT / "tests" / "tasks"

Capability = Literal["analysis", "cashflow", "financing", "editing", "interaction"]
CAPABILITIES: tuple[Capability, ...] = (
    "analysis",
    "cashflow",
    "financing",
    "editing",
    "interaction",
)


# --- Case format ----------------------------------------------------------------------


class Value(CopilotModel):
    """One value the reply must contain. Exactly one source: truth, truth_sum, tool or value."""

    truth: str | None = None  # dotted path in ground_truth.json
    plus: str | None = None  # with truth: a known amount added (e.g. an adjustment of -2000.00)
    truth_sum: list[str] = []  # several truth paths added up (e.g. three months of revenue)
    tool: str | None = None  # a tool called this turn ...
    path: str | None = None  # ... and the dotted path inside its result's data
    near_truth: str | None = None  # tool value must be within `tolerance` of this truth path
    tolerance: str | None = None  # truth path or a number
    value: str | None = None  # a literal, only with `source` saying where it comes from
    source: str | None = None
    kind: Literal["money", "percent", "date", "number"] | None = None  # None: date if ISO

    @model_validator(mode="after")
    def _one_source(self) -> Value:
        given = [self.truth, self.truth_sum or None, self.tool, self.value]
        if sum(x is not None for x in given) != 1:
            raise ValueError("a value has exactly one of truth, truth_sum, tool, value")
        if self.tool is not None and self.path is None:
            raise ValueError("a tool value needs a path")
        if self.value is not None and not self.source:
            raise ValueError("a literal value needs a source")
        if self.plus is not None and self.truth is None:
            raise ValueError("plus goes with a truth value")
        if self.near_truth is not None and (self.tool is None or self.tolerance is None):
            raise ValueError("near_truth goes with a tool value and a tolerance")
        return self


class TurnExpect(CopilotModel):
    tools: list[str] = []  # each must be called this turn (other calls are fine)
    tool_args: dict[str, dict[str, Any]] = {}  # partial match on some call of that tool
    no_tools: list[str] = []  # must not be called this turn
    values: list[Value] = []
    any_value: list[Value] = []  # at least one of these (the same fact written two ways)
    any_of: list[str] = []  # at least one phrase (case-insensitive)
    excludes: list[str] = []  # none of these (case-insensitive)
    asks_question: bool = False


class Turn(CopilotModel):
    user: str
    expect: TurnExpect = TurnExpect()


class Case(CopilotModel):
    id: str = Field(pattern=r"^T-(AN|CF|FI|ED|IX)-\d{2}$")
    capability: Capability
    title: str
    why: str
    scenario: Literal["cash_crunch", "concentrated_b2b"]
    role: Literal["viewer", "staff", "owner"] = "owner"
    mock_skip: str | None = None  # why the rule-based mock can't do this case
    turns: list[Turn]
    # Whole conversation: each tool's audit outcomes must contain these in order, and the
    # number of effects (executed or scheduled) per tool must equal `effects` (0 if absent).
    audit: dict[str, list[AuditOutcome]] = {}
    effects: dict[str, int] = {}


class CaseResult(CopilotModel):
    id: str
    capability: Capability
    title: str
    mode: str
    passed: bool
    skipped: bool = False
    failures: list[str] = []
    replies: list[str] = []
    tools: list[list[str]] = []  # per turn
    seconds: float = 0.0


def load_cases(folder: Path = CASES_DIR) -> list[Case]:
    cases = []
    for path in sorted(folder.glob("*.yaml")):
        case = Case.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if path.stem != case.id:
            raise ValueError(f"{path.name}: file name must be the case id {case.id}")
        cases.append(case)
    return cases


# --- Running ----------------------------------------------------------------------------


def run_case(case: Case, llm: LLM) -> CaseResult:
    return run_case_session(case, llm).result


def run_case_session(case: Case, llm: LLM) -> CaseRun:
    """run_case plus the finished session, for the evidence export."""
    mode = llm.name
    if case.mock_skip and isinstance(llm, RuleBasedLLM):
        skipped = CaseResult(
            id=case.id,
            capability=case.capability,
            title=case.title,
            mode=mode,
            passed=True,
            skipped=True,
            failures=[f"skipped on the mock: {case.mock_skip}"],
        )
        return CaseRun(skipped, None)
    truth = _truth(case.scenario)
    session = open_scenario(SCENARIOS_DIR / case.scenario, Role[case.role.upper()], llm=llm)
    before = session.gateway.sandbox.balances(session.actor.business_id)
    marks: list[int] = []
    shown: list[AgentReply] = []
    started = time.perf_counter()
    failures: list[str] = []
    replies: list[str] = []
    tools: list[list[str]] = []
    pool: list[Decimal] = []  # every number the model was given or the user typed

    for n, turn in enumerate(case.turns, 1):
        text = _user_text(turn.user, session)
        pool += _numbers_in_user_text(text)
        mark = len(session.history)
        marks.append(mark)
        reply = handle(text, session)
        shown.append(reply)
        new = session.history[mark:]
        results = _tool_results(new)
        for payload in results:
            pool += _numbers_in_json(payload)
        called = [t.tool for t in reply.trace]
        tools.append(called)
        replies.append(_shown(reply))
        failures += [f"turn {n}: {f}" for f in _turn_checks(turn.expect, reply, new, truth)]
        failures += [f"turn {n}: {f}" for f in _grounding(reply.text, pool)]

    failures += _audit_checks(case, session)
    result = CaseResult(
        id=case.id,
        capability=case.capability,
        title=case.title,
        mode=mode,
        passed=not failures,
        failures=failures,
        replies=replies,
        tools=tools,
        seconds=round(time.perf_counter() - started, 1),
    )
    return CaseRun(result, session, marks, shown, before)


def run_suite(cases: list[Case], llm_factory: Any) -> list[CaseResult]:
    """llm_factory: a zero-argument callable making a fresh LLM for each case."""
    return [run_case(c, llm_factory()) for c in cases]


def _truth(scenario: str) -> dict[str, Any]:
    return json.loads((SCENARIOS_DIR / scenario / "ground_truth.json").read_text(encoding="utf-8"))


def _tool_results(new: list) -> list[dict[str, Any]]:
    return [json.loads(m.content) for m in new if m.role == "tool"]


def _shown(reply: AgentReply) -> str:
    parts = [reply.text, *reply.notices]
    if reply.pending_prompt:
        parts.append(reply.pending_prompt)
    return "\n".join(p for p in parts if p)


# --- Per-turn checks ----------------------------------------------------------------------


def _turn_checks(
    expect: TurnExpect, reply: AgentReply, new: list, truth: dict[str, Any]
) -> list[str]:
    failures: list[str] = []
    called = [t.tool for t in reply.trace]
    calls = [c for m in new if m.role == "assistant" for c in m.tool_calls]
    results = {p["tool"]: p for p in _tool_results(new)}  # last result of each tool
    shown = _shown(reply)
    lowered = shown.lower()

    for tool in expect.tools:
        if tool not in called:
            failures.append(f"{tool} was not called (called: {called or 'nothing'})")
    for tool, args in expect.tool_args.items():
        made = [c.arguments for c in calls if c.name == tool]
        if made and not any(_args_match(args, a) for a in made):
            failures.append(f"{tool} arguments {made} don't include {args}")
    for tool in expect.no_tools:
        if tool in called:
            failures.append(f"{tool} was called but shouldn't be")

    for v in expect.values:
        failures += _value_problems(v, truth, results, shown)
    alternatives = [_value_problems(v, truth, results, shown) for v in expect.any_value]
    if alternatives and all(alternatives):
        names = ", ".join(_describe(v) for v in expect.any_value)
        failures.append(f"reply shows none of {names}")

    if expect.any_of and not any(p.lower() in lowered for p in expect.any_of):
        failures.append(f"reply has none of {expect.any_of}")
    for phrase in expect.excludes:
        if phrase.lower() in lowered:
            failures.append(f"reply contains {phrase!r}")
    if expect.asks_question and "?" not in reply.text:
        failures.append("reply doesn't ask a clarifying question")
    return failures


def _value_problems(v: Value, truth: dict[str, Any], results: dict, shown: str) -> list[str]:
    expected, problem = _expected(v, truth, results)
    if problem:
        return [problem]
    kind = v.kind or ("date" if isinstance(expected, date) else "money")
    if not _found(expected, kind, shown):  # type: ignore[arg-type]
        return [f"reply doesn't show {_describe(v)} = {expected}"]
    return []


def _args_match(expected: dict[str, Any], actual: Any) -> bool:
    if not isinstance(actual, dict):
        return False
    for key, want in expected.items():
        have = actual.get(key)
        a, b = _decimal(want), _decimal(have)
        if a is not None and b is not None:
            if a != b:
                return False
        elif str(want) != str(have):
            return False
    return True


def _expected(
    v: Value, truth: dict[str, Any], results: dict[str, dict]
) -> tuple[Decimal | date | None, str | None]:
    if v.truth is not None:
        base = _parse(_dig(truth, v.truth))
        if v.plus is not None and isinstance(base, Decimal):
            return base + Decimal(v.plus), None
        return base, None
    if v.truth_sum:
        return sum((Decimal(str(_dig(truth, p))) for p in v.truth_sum), Decimal(0)), None
    if v.value is not None:
        return _parse(v.value), None
    result = results.get(v.tool or "")
    if result is None or not result.get("ok"):
        return None, f"no successful {v.tool} result to read {v.path} from"
    try:
        got = _parse(_dig(result["data"], v.path or ""))
    except (KeyError, IndexError, TypeError):
        return None, f"{v.tool} result has no {v.path}"
    if v.near_truth is not None and isinstance(got, Decimal):
        want = Decimal(str(_dig(truth, v.near_truth)))
        tol = _decimal(v.tolerance)
        tol = tol if tol is not None else Decimal(str(_dig(truth, v.tolerance or "")))
        if abs(got - want) > tol:
            return None, f"{v.tool} {v.path} = {got} is off the truth {want} by more than {tol}"
    return got, None


def _dig(data: Any, path: str) -> Any:
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def _parse(raw: Any) -> Decimal | date:
    if isinstance(raw, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return date.fromisoformat(raw)
    return Decimal(str(raw))


def _decimal(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _describe(v: Value) -> str:
    if v.tool:
        return f"{v.tool}.{v.path}"
    if v.truth and v.plus:
        return f"{v.truth} {v.plus}"
    return v.truth or "+".join(v.truth_sum) or f"{v.value} ({v.source})"


# --- Matching numbers and dates in text ----------------------------------------------------

# A number as people write it: optional currency, digits with optional thousands commas and
# decimals, optional suffix (k, m, million, %).
_TOKEN = re.compile(
    r"(?<![\w.])(?P<cur>S\$|US\$|\$)?\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<suf>%|k\b|K\b|mn\b|m\b|M\b|million\b))?"
)
_SCALE = {"k": 1000, "m": 1_000_000, "mn": 1_000_000, "million": 1_000_000}


class Token(CopilotModel):
    value: Decimal  # absolute value, scaled (k, m)
    half_unit: Decimal  # the precision the text claims: half of its last written digit
    money: bool  # written with a currency sign
    percent: bool


def tokens(text: str) -> list[Token]:
    out = []
    for m in _TOKEN.finditer(text):
        num, suf = m.group("num"), (m.group("suf") or "")
        decimals = len(num.split(".")[1]) if "." in num else 0
        scale = Decimal(_SCALE.get(suf.lower(), 1))
        out.append(
            Token(
                value=Decimal(num.replace(",", "")) * scale,
                half_unit=Decimal(5).scaleb(-decimals - 1) * scale,
                money=m.group("cur") is not None,
                percent=suf == "%",
            )
        )
    return out


def _close(token: Token, target: Decimal) -> bool:
    return abs(token.value - abs(target)) <= token.half_unit


def _found(expected: Decimal | date, kind: str, text: str) -> bool:
    if kind == "date":
        return isinstance(expected, date) and _date_found(expected, text)
    assert isinstance(expected, Decimal)
    if kind == "percent":  # a ratio (0.1644) or a value already in percent (eir_pct 16.44)
        target = expected * 100 if abs(expected) <= 1 else expected
        return any(t.percent and _close(t, target) for t in tokens(text))
    return any(not t.percent and _close(t, expected) for t in tokens(text))


_MONTHS = [
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
]  # fmt: skip


def _date_found(d: date, text: str) -> bool:
    low = text.lower()
    if d.isoformat() in low:
        return True
    full = _MONTHS[d.month - 1]
    names = rf"(?:{full}|{full[:3]}\.?)"
    day = rf"0?{d.day}(?:st|nd|rd|th)?"
    patterns = (
        rf"\b{day}\s+{names}\b",  # 5 Nov, 5th November
        rf"\b{names}\s+{day}\b",  # Nov 5, November 5th
        rf"\b0?{d.day}/0?{d.month}(?:/{d.year})?\b",  # 5/11, 05/11/2026
    )
    return any(re.search(p, low) for p in patterns)


# --- Grounding (no invented or self-calculated numbers) ----------------------------------

_JSON_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _numbers_in_json(payload: Any) -> list[Decimal]:
    out = []
    for raw in _JSON_NUMBER.findall(json.dumps(payload)):
        value = _decimal(raw)
        if value is not None:
            out.append(abs(value))
    return out


def _numbers_in_user_text(text: str) -> list[Decimal]:
    return [t.value for t in tokens(text)]


def _grounding(text: str, pool: list[Decimal]) -> list[str]:
    """Every S$ amount and % the model wrote must match a number it was given."""
    failures = []
    for t in tokens(text):
        if not (t.money or t.percent):
            continue
        targets = pool if t.money else pool + [p * 100 for p in pool]
        if not any(_close(t, p) for p in targets):
            shown = f"{t.value}{'%' if t.percent else ''}"
            failures.append(f"number {shown} in the reply isn't in any tool result")
    return failures


# --- Whole-conversation checks ------------------------------------------------------------


def _audit_checks(case: Case, session: Session) -> list[str]:
    failures = []
    entries = session.gateway.audit.entries(session.actor.business_id)
    for tool, expected in case.audit.items():
        actual = iter([e.outcome for e in entries if e.tool == tool])
        if not all(any(o == want for o in actual) for want in expected):  # in-order subsequence
            got = [e.outcome for e in entries if e.tool == tool]
            failures.append(f"audit {tool}: expected {expected} in order, got {got}")
    effects: dict[str, int] = {}
    for e in entries:
        if e.outcome in _EFFECT_OUTCOMES:
            effects[e.tool] = effects.get(e.tool, 0) + 1
    for tool in set(effects) | set(case.effects):
        if effects.get(tool, 0) != case.effects.get(tool, 0):
            failures.append(
                f"{tool} took effect {effects.get(tool, 0)} time(s), "
                f"expected {case.effects.get(tool, 0)}"
            )
    return failures


# --- Report -----------------------------------------------------------------------------


def scorecard(results: list[CaseResult]) -> str:
    lines = []
    for cap in CAPABILITIES:
        group = [r for r in results if r.capability == cap]
        if not group:
            continue
        ran = [r for r in group if not r.skipped]
        passed = sum(r.passed for r in ran)
        skipped = len(group) - len(ran)
        extra = f", {skipped} skipped" if skipped else ""
        lines.append(f"{cap:<14} {passed}/{len(ran)} passed{extra}")
        for r in group:
            status = "SKIP" if r.skipped else ("PASS" if r.passed else "FAIL")
            timing = f"  ({r.seconds:.1f}s)" if r.seconds else ""
            lines.append(f"  {status}  {r.id}  {r.title}{timing}")
            lines += [f"          - {f}" for f in r.failures]
    ran = [r for r in results if not r.skipped]
    skipped = len(results) - len(ran)
    extra = f", {skipped} skipped" if skipped else ""
    lines.append(f"{'total':<14} {sum(r.passed for r in ran)}/{len(ran)} passed{extra}")
    return "\n".join(lines)


__all__ = [
    "CAPABILITIES",
    "Case",
    "CaseResult",
    "Token",
    "load_cases",
    "run_case",
    "run_case_session",
    "run_suite",
    "scorecard",
    "tokens",
]
