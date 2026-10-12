"""Known risk R3: the sandbox moves money without permission checks, so only the write tools
(which only the policy gateway runs) may call its money-moving methods, and the agent and UI
may reach tools only through the gateway."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "copilot"
MONEY_MOVERS = re.compile(
    r"\b(execute_payment|record_invoice_receipt|post_external|pay_bill_directly)\b|\.transfer\("
)
# write_tools: the agent's payments (via the gateway). policy/scheduler: the owner's scheduled
# payments when they come due (guard re-run first). sandbox/world: the scripted world.
ALLOWED_CALLERS = {
    "sandbox/bank.py",
    "sandbox/world.py",
    "tools/write_tools.py",
    "policy/scheduler.py",
}
FORBIDDEN_FOR_AGENT_AND_UI = re.compile(
    r"^\s*(from|import)\s+copilot\.(sandbox|tools|store)\b", re.MULTILINE
)


def sources():
    for path in SRC.rglob("*.py"):
        yield path.relative_to(SRC).as_posix(), path.read_text(encoding="utf-8")


def test_only_write_tools_call_money_moving_sandbox_methods():
    callers = {name for name, text in sources() if MONEY_MOVERS.search(text)}
    assert callers <= ALLOWED_CALLERS, callers - ALLOWED_CALLERS


def test_only_the_scheduler_replays_the_world():
    callers = {name for name, text in sources() if "replay_day(" in text}
    assert callers <= {"sandbox/world.py", "policy/scheduler.py"}, callers


def test_domain_tools_and_agent_never_see_the_scripted_future():
    """Known risk R12: world_events.csv holds the scenario's future. Forecasts, alerts and
    the assistant must work only from data up to the simulated today."""
    offenders = [
        name
        for name, text in sources()
        if name.startswith(
            ("analysis/", "cashflow/", "financing/", "tools/", "agent/", "ui/", "api/")
        )
        and re.search(r"world_events|sandbox\.world|WorldScript", text)
    ]
    assert offenders == []


def test_write_tools_are_run_only_by_the_gateway():
    users = {
        name for name, text in sources() if "WRITE_TOOLS" in text or "write_tools import" in text
    }
    assert users <= {"tools/write_tools.py", "tools/__init__.py", "policy/guards.py"}, users


def test_agent_and_ui_do_not_import_sandbox_tools_or_store():
    offenders = [
        name
        for name, text in sources()
        if name.startswith(("agent/", "ui/", "api/")) and FORBIDDEN_FOR_AGENT_AND_UI.search(text)
    ]
    assert offenders == []


UI_ALLOWED = {"copilot.agent", "copilot.runtime", "copilot.schemas"}


def test_ui_imports_only_agent_runtime_and_schemas():
    imports = set()
    for name, text in sources():
        if name.startswith("ui/"):
            imports |= set(re.findall(r"^\s*(?:from|import)\s+(copilot(?:\.\w+)?)", text, re.M))
    assert imports <= UI_ALLOWED, imports - UI_ALLOWED


def test_api_imports_only_agent_runtime_schemas_and_itself():
    """The API is a second UI: same layering rule, plus its own session module."""
    imports = set()
    for name, text in sources():
        if name.startswith("api/"):
            imports |= set(re.findall(r"^\s*(?:from|import)\s+(copilot(?:\.\w+)?)", text, re.M))
    allowed = UI_ALLOWED | {"copilot.api"}
    assert imports <= allowed, imports - allowed


# A bare "{amount:,.2f}" in a message drops the currency (the bug in alert messages, 2026-10-04).
# Money shown to users goes through schemas.sgd(); only that function may format this way.
BARE_MONEY = re.compile(r"\{[^{}]*:,\.2f\}")


def test_money_is_displayed_through_sgd_only():
    offenders = [
        f"{name}:{n}"
        for name, text in sources()
        for n, line in enumerate(text.splitlines(), 1)
        if BARE_MONEY.search(line) and "S$" not in line
    ]
    assert offenders == []
