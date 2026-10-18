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


def _needs_value(result: ToolResult) -> ToolResult:
    """A page needs a value: "ok but nothing to show" (e.g. no opening balance sheet) becomes
    ok=False with the tool's own reason, so pages and downloads show it instead of crashing."""
    data = result.data
    if not result.ok or getattr(data, "value", True) is not None:
        return result
    reason = data.warnings[0] if data.warnings else "Not enough data for this view."
    return result.model_copy(update={"ok": False, "message": reason})


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
    return _needs_value(_read(session, "get_financial_statements", args))


def financial_model(
    session: Session, case: str = "all", view: str = "annual", year: int = 1
) -> ToolResult:
    """The 3-year model (chunk 14a) through the gateway, as the signed-in user. Drivers come
    from the books: overrides are a chat feature, so nothing here changes them."""
    return _needs_value(
        _read(session, "get_financial_model", {"case": case, "view": view, "year": year})
    )


def valuation(
    session: Session,
    case: str = "all",
    discount_rate_pct: str | None = None,
    terminal_growth_pct: str | None = None,
    ebitda_multiple: str | None = None,
    owner_salary_monthly: str | None = None,
) -> ToolResult:
    """Break-even per case and the estimated value (chunk 14b) through the gateway, with the
    36 monthly break-even points per case for the case chart. The valuation inputs are this
    view's own inputs (nothing is saved); the model's drivers come from the books."""
    args: dict[str, Any] = {"case": case, "monthly": True}
    for key, value in (
        ("discount_rate_pct", discount_rate_pct),
        ("terminal_growth_pct", terminal_growth_pct),
        ("ebitda_multiple", ebitda_multiple),
        ("owner_salary_monthly", owner_salary_monthly),
    ):
        if value is not None:
            args[key] = value
    return _needs_value(_read(session, "get_break_even_and_value", args))


def stress_test(
    session: Session,
    shock_amount: str = "0",
    shock_date: str | None = None,
    target_pct: int = 95,
    best_plan: bool = True,
) -> ToolResult:
    """The cash-shock stress test (chunk 16a) through the gateway, with one row per day for the
    dashboard's P10-P90 band. best_plan=False skips the options search behind the headline
    (pages that show 16b's best plan get it from options_comparison instead)."""
    args: dict[str, Any] = {
        "shock_amount": shock_amount,
        "target_pct": target_pct,
        "include_daily": True,
    }
    if not best_plan:
        args["include_best_plan"] = False
    if shock_date is not None:
        args["shock_date"] = shock_date
    return _read(session, "stress_test_cash", args)


def options_comparison(
    session: Session,
    target_pct: int = 95,
    shock_amount: str = "0",
    shock_date: str | None = None,
    chase_on_time_pct: int = 50,
    customer_loss_pct: int = 0,
) -> ToolResult:
    """Every plan scored on the stress test's runs (chunk 16b) through the gateway: the options
    table, frontier, cost bridge, cash with the best plan and credit-line use per day."""
    args: dict[str, Any] = {
        "target_pct": target_pct,
        "shock_amount": shock_amount,
        "chase_on_time_pct": chase_on_time_pct,
        "customer_loss_pct": customer_loss_pct,
        "include_daily": True,
    }
    if shock_date is not None:
        args["shock_date"] = shock_date
    return _read(session, "compare_options", args)


def reconciliation(session: Session, min_severity: str = "low") -> ToolResult:
    """Reconciliation exceptions (chunk 15) through the gateway: a flat list ordered high to
    low, with counts and S$ by severity, for the dashboard's exceptions card. Read-only."""
    return _read(session, "get_reconciliation_exceptions", {"min_severity": min_severity})


def forecast(session: Session) -> ToolResult:
    """The 13-week forecast (the Overview's forecast panel) through the gateway."""
    return _read(session, "forecast_balance")


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
