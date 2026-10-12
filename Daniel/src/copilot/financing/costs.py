"""True cost of a product for the actual need: dated cash flows, total S$ cost and EIR.

Amount: enough that the cash received after upfront fees covers the need (grossed up for
fees), and at least the product's minimum (flagged as over-borrowing).
Term: the need's duration, clipped to the product's term range (flagged if longer).
Cash flows by repayment structure:
  amortising, reducing balance  equal monthly instalments (annuity), interest on what's left
  amortising, flat rate         interest = amount x rate x years, spread over equal instalments
  interest-only bullet          monthly interest, all principal at the end
  revolving / invoice           interest on the days drawn only (at least 30), repaid in one go
Upfront fees are taken on the draw date. Early-repayment fees are disclosed, not priced in.
Total cost = interest + fees. EIR = the annual rate r at which the dated flows net to zero:
sum(flow / (1 + r) ** (days / 365)) = 0 (an XIRR), found by bisection in Decimal.
Pure functions: no store, no LLM.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Literal

from copilot.cashflow.recommend import FundingNeed
from copilot.dates import add_months
from copilot.schemas import (
    CopilotModel,
    FeeKind,
    FinancingProduct,
    Money,
    ProductType,
    RateType,
    RepaymentStructure,
    sgd,
)

CENT = Decimal("0.01")
MIN_DRAWN_DAYS = 30
DAYS_PER_MONTH = 30  # converting a month term to drawn days for revolving / invoice products

FlowKind = Literal["draw", "fee", "repayment"]


class Flow(CopilotModel):
    date: date
    amount: Money  # + to the business, - from the business
    kind: FlowKind
    interest: Money = Decimal("0")  # the interest part of a repayment
    principal: Money = Decimal("0")


class Quote(CopilotModel):
    product_id: str
    product_name: str
    lender: str
    type: ProductType
    repayment: RepaymentStructure
    need_amount: Money
    amount: Money  # borrowed
    upfront_fees: Money
    amount_received: Money  # amount - upfront fees
    term_months: int
    draw_date: date
    end_date: date
    flows: list[Flow]
    total_interest: Money
    total_fees: Money
    total_cost: Money  # interest + fees
    eir_pct: Decimal  # effective annual rate, %
    instalment: Money | None  # regular monthly payment, if any
    flags: list[str]
    notes: list[str]


def _cents(x: Decimal) -> Decimal:
    return x.quantize(CENT)


def _ceil_cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_CEILING)


def upfront_fees(product: FinancingProduct, amount: Decimal) -> Decimal:
    total = Decimal("0")
    for fee in product.fees:
        if fee.kind is FeeKind.EARLY_REPAYMENT:
            continue
        total += fee.flat if fee.flat is not None else _cents(amount * fee.pct / 100)  # type: ignore[operator]
    return total


def gross_up(product: FinancingProduct, need: Decimal) -> Decimal:
    """Smallest amount whose cash received after upfront fees covers the need."""
    pct = sum(
        (f.pct for f in product.fees if f.kind is not FeeKind.EARLY_REPAYMENT and f.pct),
        Decimal("0"),
    )
    flat = sum(
        (f.flat for f in product.fees if f.kind is not FeeKind.EARLY_REPAYMENT and f.flat),
        Decimal("0"),
    )
    amount = _ceil_cents((need + flat) / (1 - pct / 100))
    while amount - upfront_fees(product, amount) < need:  # rounding of each fee
        amount += CENT
    return amount


def xirr(flows: list[tuple[date, Decimal]]) -> Decimal:
    """Annual rate r with sum(cf / (1 + r) ** (days / 365)) = 0, as a fraction."""
    start = flows[0][0]
    with localcontext() as ctx:
        ctx.prec = 20  # the rate is shown to 0.01%; 20 digits is ample

        def npv(rate: Decimal) -> Decimal:
            return sum(
                (cf / (1 + rate) ** (Decimal((d - start).days) / 365) for d, cf in flows),
                Decimal("0"),
            )

        # Money comes in first and goes out later, so the net value is -cost at 0% and
        # rises with the rate: find where it crosses zero.
        low, high = Decimal("0"), Decimal("10")
        if npv(low) >= 0:  # costs nothing
            return Decimal("0")
        for _ in range(60):  # 10 / 2**60 ~ 1e-17: far below what is shown
            mid = (low + high) / 2
            if npv(mid) < 0:
                low = mid
            else:
                high = mid
        return (low + high) / 2


def _schedule(
    product: FinancingProduct, amount: Decimal, term: int, draw: date, days: int
) -> list[Flow]:
    rate = product.annual_rate_pct / 100
    flows: list[Flow] = []
    structure = product.repayment
    if structure in (RepaymentStructure.REVOLVING, RepaymentStructure.ON_INVOICE_SETTLEMENT):
        interest = _cents(amount * rate * days / 365)
        flows.append(
            Flow(
                date=draw + timedelta(days=days),
                amount=-(amount + interest),
                kind="repayment",
                interest=interest,
                principal=amount,
            )
        )
    elif structure is RepaymentStructure.INTEREST_ONLY_BULLET:
        monthly = _cents(amount * rate / 12)
        for k in range(1, term + 1):
            principal = amount if k == term else Decimal("0")
            flows.append(
                Flow(
                    date=add_months(draw, k),
                    amount=-(monthly + principal),
                    kind="repayment",
                    interest=monthly,
                    principal=principal,
                )
            )
    elif product.rate_type is RateType.FLAT:
        interest_total = _cents(amount * rate * term / 12)
        principal_each, interest_each = _cents(amount / term), _cents(interest_total / term)
        for k in range(1, term + 1):
            last = k == term
            principal = amount - principal_each * (term - 1) if last else principal_each
            interest = interest_total - interest_each * (term - 1) if last else interest_each
            flows.append(
                Flow(
                    date=add_months(draw, k),
                    amount=-(principal + interest),
                    kind="repayment",
                    interest=interest,
                    principal=principal,
                )
            )
    else:  # amortising, reducing balance: annuity
        r = rate / 12
        payment = _cents(amount / term) if r == 0 else _cents(amount * r / (1 - (1 + r) ** -term))
        balance = amount
        for k in range(1, term + 1):
            interest = _cents(balance * r)
            principal = balance if k == term else payment - interest
            balance -= principal
            flows.append(
                Flow(
                    date=add_months(draw, k),
                    amount=-(principal + interest),
                    kind="repayment",
                    interest=interest,
                    principal=principal,
                )
            )
    return flows


def quote(product: FinancingProduct, need: FundingNeed) -> Quote:
    need_months = need.duration_months
    term = min(max(need_months, product.min_term_months), product.max_term_months)
    grossed = gross_up(product, need.amount)
    amount = max(grossed, product.min_amount)
    fees = upfront_fees(product, amount)
    drawn_days = 0
    if product.repayment in (
        RepaymentStructure.REVOLVING,
        RepaymentStructure.ON_INVOICE_SETTLEMENT,
    ):
        drawn_days = min(
            max(need.duration_days, MIN_DRAWN_DAYS), product.max_term_months * DAYS_PER_MONTH
        )
        term = max(1, round(drawn_days / DAYS_PER_MONTH))
    flows = [Flow(date=need.draw_date, amount=amount, kind="draw", principal=amount)]
    if fees:
        flows.append(Flow(date=need.draw_date, amount=-fees, kind="fee"))
    repayments = _schedule(product, amount, term, need.draw_date, drawn_days)
    flows += repayments
    interest = sum((f.interest for f in repayments), Decimal("0"))

    flags: list[str] = []
    if amount > grossed:
        flags.append(
            f"Minimum loan is {sgd(product.min_amount)}: you'd borrow "
            f"{sgd(amount - fees - need.amount)} more than you need."
        )
    elif fees:
        flags.append(f"Borrow {sgd(amount)} so that {sgd(need.amount)} is left after fees.")
    if drawn_days == 0 and term > need_months:
        flags.append(
            f"Shortest term is {product.min_term_months} months; you need about {need_months}."
        )
    if drawn_days and drawn_days > need.duration_days:
        flags.append(f"Interest is charged for at least {MIN_DRAWN_DAYS} days.")
    longest = product.max_term_months
    if (drawn_days and need.duration_days > longest * DAYS_PER_MONTH) or (
        not drawn_days and need_months > longest
    ):
        flags.append(
            f"Longest term is {longest} months; you need about {need_months}, so you'd have to "
            "repay or refinance before then."
        )
    if need.duration_is_lower_bound:
        flags.append(
            "Your cash hasn't recovered by the end of the forecast, so you may need it for "
            "longer, and the cost would be higher."
        )
    notes = [
        f"Early repayment fee: {f.pct.normalize():f}% of the amount repaid early."  # type: ignore[union-attr]
        if f.pct is not None
        else f"Early repayment fee: {sgd(f.flat)}."  # type: ignore[arg-type]
        for f in product.fees
        if f.kind is FeeKind.EARLY_REPAYMENT
    ]
    instalments = {f.amount for f in repayments[:-1]} if len(repayments) > 1 else set()
    eir = xirr([(f.date, f.amount) for f in flows])
    return Quote(
        product_id=product.id,
        product_name=product.name,
        lender=product.lender,
        type=product.type,
        repayment=product.repayment,
        need_amount=need.amount,
        amount=amount,
        upfront_fees=fees,
        amount_received=amount - fees,
        term_months=term,
        draw_date=need.draw_date,
        end_date=repayments[-1].date,
        flows=flows,
        total_interest=interest,
        total_fees=fees,
        total_cost=interest + fees,
        eir_pct=(eir * 100).quantize(CENT),
        instalment=-instalments.pop() if len(instalments) == 1 else None,
        flags=flags,
        notes=notes,
    )
