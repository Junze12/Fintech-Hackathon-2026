"""How much financing is needed, for how long, and where that figure comes from.

Non-borrowing first (CLAUDE.md): by default the need is what remains after the non-borrowing
plan in cashflow/recommend.py. If that plan closes every gap, there is no need, and we say
so. A need stated by the user (amount and months) is used as given, with a note if the
forecast disagrees. If only one of the two is given and the forecast can't supply the other,
we ask instead of guessing.
Read-only: never writes.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Literal

from copilot.cashflow.forecast import Forecast, ForecastItem
from copilot.cashflow.recommend import (
    FUNDING_PURPOSE,
    FundingNeed,
    Recommendations,
    recommend_actions,
)
from copilot.cashflow.scenarios import apply_changes
from copilot.dates import add_months
from copilot.schemas import CopilotModel, DomainResult, sgd
from copilot.store import Store

MAX_NEED = Decimal("10000000.00")
MAX_MONTHS = 120


class NeedAssessment(CopilotModel):
    need: FundingNeed | None
    source: Literal["forecast", "user", "none"]
    plan_steps: list[str]  # non-borrowing steps assumed done (titles)
    forecast_need: FundingNeed | None  # what the forecast says, for comparison
    question: str | None  # set when we must ask the user before matching
    message: str


def assess_need(
    store: Store,
    business_id: str,
    forecast: DomainResult[Forecast],
    amount: Decimal | None = None,
    months: int | None = None,
    purpose: str | None = None,
    buffer: Decimal = Decimal("0"),
) -> tuple[NeedAssessment, list[ForecastItem], Recommendations]:
    """The need, plus the forecast items with the non-borrowing plan applied."""
    if amount is not None and not 0 < amount <= MAX_NEED:
        raise ValueError(f"amount must be between S$0.01 and {sgd(MAX_NEED)}")
    if months is not None and not 1 <= months <= MAX_MONTHS:
        raise ValueError(f"months must be between 1 and {MAX_MONTHS}")
    fc = forecast.value
    rec = recommend_actions(store, business_id, forecast, buffer).value
    plan = [o for o in rec.options if o.in_plan]
    items, _, _ = apply_changes(store, business_id, fc, [c for o in plan for c in o.changes])
    steps = [o.title for o in plan]
    from_forecast = rec.funding_need

    def result(need, source, message, question=None):
        return (
            NeedAssessment(
                need=need,
                source=source,
                plan_steps=steps,
                forecast_need=from_forecast,
                question=question,
                message=message,
            ),
            items,
            rec,
        )

    if amount is None and months is None:
        if from_forecast is None:
            return result(None, "none", rec.message)
        return result(
            from_forecast,
            "forecast",
            f"From your forecast: about {sgd(from_forecast.amount)} from "
            f"{from_forecast.draw_date.isoformat()}"
            + (" (after the steps without borrowing)." if steps else "."),
        )

    draw = fc.as_of + timedelta(days=1)
    if amount is None or months is None:
        if from_forecast is None:
            missing = "how much" if amount is None else "for how long"
            return result(
                None,
                "none",
                f"Your forecast shows no gap to fill, so I need to know {missing} you want to "
                "borrow.",
                question=f"Please tell me {missing} you need.",
            )
        amount = amount if amount is not None else from_forecast.amount
        months = months if months is not None else from_forecast.duration_months
        draw = from_forecast.draw_date  # the gap the forecast found starts then

    repay = add_months(draw, months)
    need = FundingNeed(
        amount=amount,
        target=buffer,
        draw_date=draw,
        repay_date=repay,
        duration_days=(repay - draw).days,
        duration_months=months,
        duration_is_lower_bound=False,
        purpose=purpose or FUNDING_PURPOSE,
        basis="stated by the user",
    )
    note = (
        "Your forecast shows no cash gap, so borrowing isn't needed for that; matching your "
        "stated need anyway."
        if from_forecast is None
        else f"Your forecast suggests about {sgd(from_forecast.amount)}; matching what you asked."
    )
    length = f"{months} month" + ("s" if months != 1 else "")
    return result(need, "user", f"Matching {sgd(amount)} for {length}. {note}")
