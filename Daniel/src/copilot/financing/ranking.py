"""Match the business to financing products: eligibility for every product, then rank the
eligible ones (agreed 2026-10-05).

1. Need: financing/needs.py (after the non-borrowing plan, or as stated by the user).
2. Eligibility for every product, with reasons (financing/eligibility.py). Products the
   business fails, can't be verified for, or that can't lend enough are never ranked.
3. Each eligible product is priced for the need (financing/costs.py), and its draw and
   repayments are added to the forecast (with the non-borrowing plan applied) to see whether
   cash stays at or above the target for the 13 weeks.
4. Order: keeps cash above target first, then lowest total S$ cost, then (only if cash flow
   is volatile: a month with negative net cash flow in the last 6) more flexible repayment.
Read-only: never writes.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from copilot.cashflow.forecast import (
    Forecast,
    ForecastItem,
    balance_path,
    find_gaps,
    horizon_end,
)
from copilot.cashflow.summary import cash_summary
from copilot.dates import add_months
from copilot.financing.catalogue import Catalogue, load_catalogue
from copilot.financing.costs import Quote, quote
from copilot.financing.eligibility import Eligibility, Fact, business_facts, check
from copilot.financing.needs import NeedAssessment, assess_need
from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    UNTRUSTED,
    CopilotModel,
    DomainResult,
    Money,
    RepaymentStructure,
    sgd,
)
from copilot.store import Store

VOLATILITY_MONTHS = 6
DISCLAIMER = "Approval is the lender's decision; these are illustrative terms, not offers."
# More flexible first: repay as soon as cash comes in > fixed date > fixed instalments.
FLEXIBILITY = {
    RepaymentStructure.REVOLVING: 0,
    RepaymentStructure.ON_INVOICE_SETTLEMENT: 1,
    RepaymentStructure.INTEREST_ONLY_BULLET: 2,
    RepaymentStructure.AMORTISING: 3,
}
Message = Annotated[str, UNTRUSTED]  # quotes plan steps (counterparty names)


class RankedQuote(CopilotModel):
    rank: int
    quote: Quote
    keeps_cash_above_target: bool
    lowest_with_loan: Money
    lowest_with_loan_date: date
    repayments_after_forecast: int  # repayments beyond the 13 weeks (not checked)


class FinancingMatch(CopilotModel):
    need: NeedAssessment
    facts: list[Fact]
    eligibility: list[Eligibility]  # every product, eligible or not
    ranked: list[RankedQuote]
    volatile: bool
    disclaimer: str
    message: Message


def is_volatile(store: Store, business_id: str, as_of: date) -> bool:
    start = add_months(date(as_of.year, as_of.month, 1), -VOLATILITY_MONTHS)
    end = date(as_of.year, as_of.month, 1) - timedelta(days=1)
    summary = cash_summary(store, business_id, start, end).value
    return any(p.net < 0 for p in summary.periods)


def loan_items(q: Quote) -> list[ForecastItem]:
    return [
        ForecastItem(
            date=f.date,
            amount=f.amount,
            source="what_if",
            label=f"{q.product_name}: {f.kind}",
        )
        for f in q.flows
    ]


def _message(
    need: NeedAssessment, ranked: list[RankedQuote], eligibility: list[Eligibility]
) -> str:
    if need.need is None:
        return need.question or (
            f"{need.message} If you still want to compare financing, tell me how much and for "
            "how long."
        )
    ineligible = sum(1 for e in eligibility if not e.eligible)
    if not ranked:
        return (
            f"{need.message} None of the {len(eligibility)} products fit: the business isn't "
            "eligible for them or they can't lend this amount."
        )
    top = ranked[0]
    q = top.quote
    if top.keeps_cash_above_target:
        horizon = "for the whole 13-week forecast"
        fit = f"keeps cash above {sgd(need.need.target)} {horizon}"
    else:
        fit = "is the cheapest, but no option keeps cash above the target for all 13 weeks"
    steps = (
        f" This assumes the steps without borrowing are taken first: {'; '.join(need.plan_steps)}."
        if need.plan_steps
        else ""
    )
    return (
        f"{need.message} Best fit: {q.product_name} from {q.lender}. Borrow {sgd(q.amount)} "
        f"for {q.term_months} month{'s' if q.term_months != 1 else ''}: total cost "
        f"{sgd(q.total_cost)}, effective annual rate "
        f"{q.eir_pct}%. It {fit}.{steps} {len(ranked) - 1} other option(s) shown; "
        f"{ineligible} product(s) not eligible. {DISCLAIMER}"
    )


def match_financing(
    store: Store,
    sandbox: Sandbox,
    business_id: str,
    forecast: DomainResult[Forecast],
    amount: Decimal | None = None,
    months: int | None = None,
    purpose: str | None = None,
    buffer: Decimal = Decimal("0"),
    catalogue: Catalogue | None = None,
) -> DomainResult[FinancingMatch]:
    catalogue = catalogue or load_catalogue()
    fc = forecast.value
    need, plan_items, _ = assess_need(store, business_id, forecast, amount, months, purpose, buffer)
    facts = business_facts(store, sandbox, business_id, fc.as_of)
    eligibility = [check(p, facts.value) for p in catalogue.products]
    volatile = is_volatile(store, business_id, fc.as_of)
    last_day = horizon_end(fc.as_of)

    ranked: list[RankedQuote] = []
    too_small: dict[str, str] = {}  # passed its rules but can't lend enough for this need
    if need.need is not None:
        target = need.need.target
        candidates = []
        for product, elig in zip(catalogue.products, eligibility, strict=True):
            if not elig.eligible:
                continue
            q = quote(product, need.need)
            if q.amount > elig.max_amount:
                too_small[product.id] = (
                    f"can lend at most {sgd(elig.max_amount)}; this needs {sgd(q.amount)}"
                )
                continue
            path = balance_path(fc.as_of, fc.start_balance, plan_items + loan_items(q))
            low_day, low = min(path, key=lambda db: db[1])
            candidates.append(
                (
                    not find_gaps(path, target),
                    q,
                    low,
                    low_day,
                    sum(1 for f in q.flows if f.date > last_day),
                )
            )
        candidates.sort(
            key=lambda c: (
                not c[0],
                c[1].total_cost,
                FLEXIBILITY[c[1].repayment] if volatile else 0,
                c[1].product_id,
            )
        )
        ranked = [
            RankedQuote(
                rank=i,
                quote=q,
                keeps_cash_above_target=keeps,
                lowest_with_loan=low,
                lowest_with_loan_date=low_day,
                repayments_after_forecast=later,
            )
            for i, (keeps, q, low, low_day, later) in enumerate(candidates, start=1)
        ]
    eligibility = [
        e.model_copy(update={"eligible": False, "reasons": [*e.reasons, too_small[e.product_id]]})
        if e.product_id in too_small
        else e
        for e in eligibility
    ]

    warnings = list(facts.warnings)
    if any(r.repayments_after_forecast for r in ranked):
        warnings.append(
            "Repayments after the 13-week forecast aren't checked against your cash; make sure "
            "the business can meet them."
        )
    return DomainResult[FinancingMatch](
        value=FinancingMatch(
            need=need,
            facts=facts.value.facts,
            eligibility=eligibility,
            ranked=ranked,
            volatile=volatile,
            disclaimer=f"{DISCLAIMER} {catalogue.disclaimer}",
            message=_message(need, ranked, eligibility),
        ),
        data_coverage=forecast.data_coverage,
        warnings=warnings,
    )


def find_eligible(match: FinancingMatch, product_id: str) -> RankedQuote | None:
    return next((r for r in match.ranked if r.quote.product_id == product_id), None)
