"""Read-only views for the UI's side panels and the API's dashboard.

They go through the same policy gateway as the agent, as the signed-in user, so panels are
role-checked and audited like everything else. They never write.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from copilot.agent.state import Session
from copilot.dates import add_months
from copilot.policy.gateway import ToolResult


def today(session: Session) -> date:
    return session.gateway.today(session.actor)


def _read(session: Session, tool: str, args: dict[str, Any] | None = None) -> ToolResult:
    return session.gateway.call(session.actor, tool, args or {})


def statements(
    session: Session,
    period: str = "month",
    month: str | None = None,
    statement: str = "all",
    view: str = "with_adjustments",
) -> ToolResult:
    """Accrual statements (chunk 12) through the gateway, as the signed-in user."""
    args: dict[str, Any] = {"period": period, "statement": statement, "view": view}
    if month is not None:
        args["month"] = month
    return _read(session, "get_financial_statements", args)


def adjustments(session: Session) -> ToolResult:
    """Recorded adjustments and saved forecast assumptions (chunk 13), read-only."""
    return _read(session, "list_adjustments")


def cash_panel(session: Session):
    """CashPosition (accounts + total), or None if unavailable."""
    result = _read(session, "get_cash_position")
    return result.data.value if result.ok else None


def alert_panel(session: Session) -> list | None:
    """Ranked CashAlerts (most important first); [] if none, None if they can't be computed."""
    result = _read(session, "get_alerts")
    return result.data["alerts"].value if result.ok else None


def pending_panel(session: Session) -> str | None:
    """The action waiting for this user's confirmation, with its code, if any."""
    action = session.gateway.pending(session.actor)
    return action.prompt if action is not None else None


def last_full_quarter(session: Session) -> tuple[date, date]:
    """The three whole calendar months before the current one (the dashboard's metrics period)."""
    end = today(session).replace(day=1) - timedelta(days=1)
    return add_months(end + timedelta(days=1), -3), end


def dashboard_panels(session: Session) -> dict[str, ToolResult]:
    """Every dashboard panel as a full ToolResult (ok, message, data), one gateway call each.

    A panel the user's role can't see, or that fails, comes back with ok=False and the
    gateway's reason; the other panels are unaffected.
    """
    start, end = last_full_quarter(session)
    period = {"start": start.isoformat(), "end": end.isoformat()}
    return {
        "cash": _read(session, "get_cash_position"),
        "forecast": _read(session, "forecast_balance"),
        "alerts": _read(session, "get_alerts"),
        "metrics": _read(session, "get_metrics", period),
        "ageing": _read(session, "get_ageing"),
        "trend": _read(session, "get_cash_trend"),
        "health": _read(session, "get_health_ratios"),
        "financing": _read(session, "find_financing"),
    }
