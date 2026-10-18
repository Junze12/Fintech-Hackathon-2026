"""The demo's simulated clock, for the UI. Kept apart from views.py because it changes state.

Advancing goes through the policy gateway as the signed-in user: it replays what happens in
the simulated world, runs the owner's scheduled payments (re-checked first) and reports any
new alerts. It is not offered to the LLM, so chat text can never move the clock.
"""

from __future__ import annotations

from copilot.agent.state import Session


def advance(session: Session, days: int):
    """ClockReport: what happened, payments run, new alerts; ok=False with a reason if refused."""
    return session.gateway.advance_clock(session.actor, days)
