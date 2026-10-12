"""Composition root: builds a ready-to-use session. The only module that wires every layer.

The UI imports this and copilot.agent, nothing lower. Each call creates a fresh in-memory
database, so every demo session starts clean.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4

from copilot.agent.llm import LLM
from copilot.agent.mock_rules import RuleBasedLLM
from copilot.agent.state import Session
from copilot.ingest import ingest_folder
from copilot.policy.gateway import Gateway
from copilot.policy.roles import Actor
from copilot.sandbox.bank import Sandbox
from copilot.sandbox.world import WorldScript
from copilot.schemas import Business, Role
from copilot.store import Store

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS: dict[str, Path] = {
    "Straits Harbour Distribution (cash crunch)": ROOT / "data" / "synthetic" / "cash_crunch",
    "Clearpath Systems (concentrated customers)": ROOT / "data" / "synthetic" / "concentrated_b2b",
    "Straits Harbour, poisoned data (red-team)": ROOT / "data" / "synthetic" / "prompt_injection",
}


def make_llm(kind: str, effort: str = "") -> LLM:
    """ "claude" = the real model (needs ANTHROPIC_API_KEY, see agent/claude.py); "mock" = the
    rule-based demo assistant, which needs no key or network. `effort` overrides
    COPILOT_EFFORT for Claude (the eval's --effort); empty keeps the configured default."""
    if kind == "claude":
        from copilot.agent.claude import ClaudeLLM  # imported lazily: tests never need the SDK

        return ClaudeLLM(effort=effort)
    if kind == "mock":
        return RuleBasedLLM()
    raise ValueError(f"unknown LLM kind {kind!r}")


def open_scenario(
    folder: Path, role: Role, llm: LLM | None = None, also_load: tuple[Path, ...] = ()
) -> Session:
    """Load a scenario folder into a fresh sandbox and sign in a demo user with `role`.

    The folder's world_events.csv (if any) is handed to the gateway, which replays it when the
    clock is advanced. Nothing else ever reads it. `also_load` puts other businesses in the
    same database (the red-team suite uses it to probe cross-business access); the user is
    signed in to the first business only.
    """
    store = Store(":memory:", any_thread=True)  # one session, used from Streamlit reruns
    sandbox = Sandbox(store)
    business = _load(store, sandbox, folder)
    for other in also_load:
        _load(store, sandbox, other)
    actor = Actor(
        user_id=f"demo-{role.label}",
        role=role,
        business_id=business.id,
        session_id=f"s-{uuid4().hex[:12]}",
    )
    return Session(
        actor=actor,
        gateway=Gateway(store, sandbox, world=WorldScript.load(folder)),
        llm=llm or RuleBasedLLM(),
        business_name=business.name,
    )


def _load(store: Store, sandbox: Sandbox, folder: Path) -> Business:
    business = ingest_folder(store, folder).imported.business
    truth = folder / "ground_truth.json"
    if truth.exists():  # start the clock at the scenario's as-of date
        as_of = json.loads(truth.read_text(encoding="utf-8"))["as_of"]
        sandbox.set_today(business.id, date.fromisoformat(as_of))
    return business
