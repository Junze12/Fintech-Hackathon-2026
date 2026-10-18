"""Break-even per case and an estimated value of the business (chunk 14b).

Both read the 3-year model (model.py) and change nothing; every request rebuilds them.

Break-even (accrual, operating level, before interest): monthly sales needed to cover the
month's operating expenses at the case's gross margin, i.e. operating expenses / (1 - cost of
sales %). Shown beside today's two figures, each with its basis: cash (health.break_even_sales,
last 3 months) and accrual (the last 12 months of statements, same formula as the cases).

Valuation (decided with Daniel 2026-10-13), an estimate, not advice and not a price:
  free cash flow (year n) = model operating cash flow + interest added back
                            - owner salary x 12 - tax (17% of positive operating profit)
  DCF  = sum FCF_n / (1 + r)^n + terminal value / (1 + r)^3,
         terminal value = FCF_3 x (1 + g) / (r - g)          r 20%, g 2% (our assumptions)
  EBITDA multiple = 4x the projected year-1 EBITDA (our assumption)
  equity value = enterprise value + cash - loans - other borrowings (balance sheet at start)
Not meaningful (value None with the reason, never a made-up figure): a DCF when year-3 free
cash flow is zero or negative; a multiple when year-1 EBITDA is zero or negative or under 2%
of sales. Every S$ is rounded to cents at the step it is shown, so totals add up exactly.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import Field

from copilot.analysis.health import break_even_sales
from copilot.analysis.model import (
    CASE_NAMES,
    CASES,
    MONTHS,
    ModelDriver,
    ModelInputs,
    ModelLoan,
    _base,
    model_from_base,
)
from copilot.analysis.statements import month_end, month_label, month_start
from copilot.schemas import CopilotModel, DataCoverage, DomainResult, Driver, Money, sgd
from copilot.store import Store

CENT = Decimal("0.01")
RATIO = Decimal("0.0001")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")

# Defaults (decided 2026-10-13): our assumptions, not data.
DISCOUNT_RATE = Decimal("20")
TERMINAL_GROWTH = Decimal("2")
EBITDA_MULTIPLE = Decimal("4")
TAX_RATE = Decimal("17")  # Singapore headline corporate rate
TERMINAL_SHARE_WARNING = Decimal("0.60")
MIN_EBITDA_MARGIN = Decimal("0.02")
RATE_STEP = Decimal("5")
GROWTH_STEPS = (Decimal("-2"), Decimal("0"), Decimal("1"))
MULTIPLE_STEP = Decimal("1")

DISCLAIMER = (
    "An estimate from your books and the stated assumptions, not advice and not a price. "
    "A buyer or lender would do their own valuation."
)
YOURS = "your figure for this question"
OURS = "our assumption, not data"


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


# --- Inputs ----------------------------------------------------------------------------------


class ValueInputs(CopilotModel):
    """Overrides for the valuation (None = our default). Nothing is saved."""

    discount_rate_pct: Decimal | None = Field(default=None, ge=5, le=50)
    terminal_growth_pct: Decimal | None = Field(default=None, ge=-2, le=5)
    ebitda_multiple: Decimal | None = Field(default=None, ge=1, le=10)
    owner_salary_monthly: Money | None = Field(default=None, ge=0, le=100_000)


# --- Result models ---------------------------------------------------------------------------


class BreakEvenNow(CopilotModel):
    """Today's break-even on one basis, over a stated period."""

    basis: Literal["cash", "accrual"]
    period_start: date
    period_end: date
    avg_monthly_sales: Money
    avg_monthly_fixed_costs: Money
    gross_margin: Decimal | None  # fraction
    break_even_monthly_sales: Money | None  # None when the margin is zero or negative
    headroom: Money | None  # sales - break-even (negative = below)


class BreakEvenPoint(CopilotModel):
    """One month of a case, for a break-even line on the case chart."""

    month: str
    sales: Money
    fixed_costs: Money
    break_even_sales: Money | None


class BreakEvenYear(CopilotModel):
    year: int
    months: str
    avg_monthly_sales: Money
    avg_monthly_fixed_costs: Money
    break_even_monthly_sales: Money | None
    headroom: Money | None


class CaseBreakEven(CopilotModel):
    case: str
    name: str
    basis: Literal["accrual"] = "accrual"
    gross_margin: Decimal  # fraction: 1 - the case's cost of sales %
    years: list[BreakEvenYear]
    first_month_reached: str | None  # YYYY-MM; None = not within the 3 years
    months_below: int  # of the 36
    status: str  # one sentence built by code
    monthly: list[BreakEvenPoint]


class BreakEvenView(CopilotModel):
    today_cash: BreakEvenNow
    today_accrual: BreakEvenNow
    cases: dict[str, CaseBreakEven]


class ValuationInput(CopilotModel):
    key: str
    label: str
    value: Decimal
    unit: str
    source: str


class ValuationYear(CopilotModel):
    year: int
    months: str
    revenue: Money
    ebitda: Money  # after the owner salary, if one is given
    operating_profit: Money  # after the owner salary
    owner_salary: Money
    tax: Money
    operating_cash_flow: Money  # from the model (after interest)
    interest_added_back: Money
    free_cash_flow: Money
    discount_factor: Decimal  # 1 / (1 + r)^n, 6 places
    present_value: Money


class Dcf(CopilotModel):
    present_value_years_1_3: Money
    terminal_value: Money | None
    present_value_terminal: Money | None
    terminal_share: Decimal | None  # fraction of the enterprise value
    enterprise_value: Money | None
    equity_value: Money | None
    not_meaningful: str | None  # the reason when there is no value


class MultipleValue(CopilotModel):
    year1_ebitda: Money
    ebitda_margin: Decimal | None  # fraction of year-1 sales
    multiple: Decimal
    enterprise_value: Money | None
    equity_value: Money | None
    not_meaningful: str | None


class SensitivityCell(CopilotModel):
    input: Decimal  # the rate / growth % or the multiple tried
    equity_value: Money | None  # None where not meaningful


class Sensitivity(CopilotModel):
    discount_rate_pct: list[SensitivityCell]  # at the chosen terminal growth
    terminal_growth_pct: list[SensitivityCell]  # at the chosen discount rate
    ebitda_multiple: list[SensitivityCell]


class CaseValuation(CopilotModel):
    case: str
    name: str
    years: list[ValuationYear]
    dcf: Dcf
    multiple: MultipleValue
    sensitivity: Sensitivity


class EquityBridge(CopilotModel):
    """From enterprise value to equity value, at the balance sheet the model opens from."""

    as_of: date
    cash: Money
    loans: Money
    other_borrowings: Money
    net_debt: Money  # loans + other borrowings - cash (negative = net cash)
    loan_list: list[ModelLoan]


class ValuationView(CopilotModel):
    disclaimer: str
    inputs: list[ValuationInput]
    model_drivers: list[ModelDriver]  # the 3-year model's drivers, with their sources
    bridge: EquityBridge
    book_equity: Money  # net assets on the balance sheet: an accounting value, not a price
    cases: dict[str, CaseValuation]


class BusinessValue(CopilotModel):
    starts_from: date
    first_month: str
    last_month: str
    break_even: BreakEvenView | None  # None when only the valuation was asked for
    valuation: ValuationView | None


# --- Break-even ------------------------------------------------------------------------------


def _break_even(fixed: Decimal, margin: Decimal) -> Decimal | None:
    return _round(fixed / margin) if margin > 0 else None


def _case_break_even(case, name: str, cost_of_sales_pct: Decimal) -> CaseBreakEven:
    margin = (HUNDRED - cost_of_sales_pct) / HUNDRED
    points = [
        BreakEvenPoint(
            month=m.month,
            sales=m.pnl.revenue,
            fixed_costs=m.pnl.total_operating_expenses,
            break_even_sales=_break_even(m.pnl.total_operating_expenses, margin),
        )
        for m in case.monthly
    ]
    years = []
    for i, y in enumerate(case.years):
        chunk = points[i * 12 : (i + 1) * 12]
        fixed = sum((p.fixed_costs for p in chunk), ZERO) / len(chunk)
        sales = _round(y.pnl.revenue / len(chunk))
        be = _break_even(fixed, margin)
        years.append(
            BreakEvenYear(
                year=y.year,
                months=y.months,
                avg_monthly_sales=sales,
                avg_monthly_fixed_costs=_round(fixed),
                break_even_monthly_sales=be,
                headroom=None if be is None else sales - be,
            )
        )
    hit = [p.break_even_sales is not None and p.sales >= p.break_even_sales for p in points]
    start = hit.index(True) if any(hit) else None
    first = None if start is None else points[start].month
    below = MONTHS - sum(hit)
    if first is None:
        status = "Sales stay below break-even for all 3 years."
    elif below == 0:
        status = "Sales are at or above break-even every month."
    elif all(hit[start:]):
        status = f"Sales reach break-even in {month_label(first)} and stay above it."
    else:
        status = (
            f"Sales first reach break-even in {month_label(first)} but are below it in "
            f"{below} of the 36 months."
        )
    return CaseBreakEven(
        case=case.case,
        name=name,
        gross_margin=margin.quantize(RATIO),
        years=years,
        first_month_reached=first,
        months_below=below,
        status=status,
        monthly=points,
    )


def _today_accrual(base) -> BreakEvenNow:
    n = len(base.last12)
    revenue = sum((m.pnl.revenue for m in base.last12), ZERO)
    gross = sum((m.pnl.gross_profit for m in base.last12), ZERO)
    fixed = sum((m.pnl.total_operating_expenses for m in base.last12), ZERO)
    margin = (gross / revenue).quantize(RATIO) if revenue > 0 else None
    sales = _round(revenue / n)
    be = _break_even(fixed / n, margin) if margin is not None else None
    return BreakEvenNow(
        basis="accrual",
        period_start=month_start(base.last12[0].month),
        period_end=month_end(month_start(base.last12[-1].month)),
        avg_monthly_sales=sales,
        avg_monthly_fixed_costs=_round(fixed / n),
        gross_margin=margin,
        break_even_monthly_sales=be,
        headroom=None if be is None else sales - be,
    )


def _today_cash(store: Store, business_id: str, today: date) -> BreakEvenNow:
    h = break_even_sales(store, business_id, today).value
    return BreakEvenNow(
        basis="cash",
        period_start=h.start,
        period_end=h.end,
        avg_monthly_sales=h.avg_monthly_revenue,
        avg_monthly_fixed_costs=h.avg_monthly_fixed_costs,
        gross_margin=h.gross_margin,
        break_even_monthly_sales=h.break_even_monthly_sales,
        headroom=h.headroom,
    )


# --- Valuation -------------------------------------------------------------------------------


def _factor(rate: Decimal, n: int) -> Decimal:
    return (1 + rate / HUNDRED) ** n


def _dcf(fcf: list[Decimal], rate: Decimal, growth: Decimal, net_debt: Decimal) -> Dcf:
    pv_years = sum((_round(f / _factor(rate, i + 1)) for i, f in enumerate(fcf)), ZERO)
    if fcf[-1] <= 0:
        return Dcf(
            present_value_years_1_3=pv_years,
            terminal_value=None,
            present_value_terminal=None,
            terminal_share=None,
            enterprise_value=None,
            equity_value=None,
            not_meaningful=(
                f"Free cash flow in year 3 is {sgd(fcf[-1])}: the business uses cash at the end "
                "of the projection, so a going-concern value isn't meaningful on these figures."
            ),
        )
    terminal = _round(fcf[-1] * (1 + growth / HUNDRED) / ((rate - growth) / HUNDRED))
    pv_terminal = _round(terminal / _factor(rate, len(fcf)))
    ev = pv_years + pv_terminal
    share = (pv_terminal / ev).quantize(RATIO) if ev > 0 else None
    return Dcf(
        present_value_years_1_3=pv_years,
        terminal_value=terminal,
        present_value_terminal=pv_terminal,
        terminal_share=share,
        enterprise_value=ev,
        equity_value=ev - net_debt,
        not_meaningful=None,
    )


def _multiple(ebitda: Decimal, revenue: Decimal, multiple: Decimal, net_debt: Decimal):
    margin = (ebitda / revenue).quantize(RATIO) if revenue > 0 else None
    reason = None
    if ebitda <= 0:
        reason = f"Year-1 EBITDA is {sgd(ebitda)}: a multiple of a loss isn't meaningful."
    elif margin is None or margin < MIN_EBITDA_MARGIN:
        reason = (
            f"Year-1 EBITDA is {sgd(ebitda)}, under 2% of sales: too thin for a multiple to "
            "mean anything."
        )
    ev = None if reason else _round(ebitda * multiple)
    return MultipleValue(
        year1_ebitda=ebitda,
        ebitda_margin=margin,
        multiple=multiple,
        enterprise_value=ev,
        equity_value=None if ev is None else ev - net_debt,
        not_meaningful=reason,
    )


def _steps(base: Decimal, steps, lower: Decimal, upper: Decimal) -> list[Decimal]:
    return [base + s for s in steps if lower <= base + s <= upper]


def _case_valuation(
    case, name: str, rate: Decimal, growth: Decimal, multiple: Decimal, salary: Decimal,
    net_debt: Decimal,
) -> CaseValuation:  # fmt: skip
    salary_year = salary * 12
    years = []
    for y in case.years:
        p = y.pnl
        dep = p.operating_expenses.get("depreciation", ZERO)
        operating = p.operating_profit - salary_year
        tax = _round(max(operating, ZERO) * TAX_RATE / HUNDRED)
        fcf = y.cash_flow.operating + p.interest - salary_year - tax
        factor = _factor(rate, y.year)
        years.append(
            ValuationYear(
                year=y.year,
                months=y.months,
                revenue=p.revenue,
                ebitda=operating + dep,
                operating_profit=operating,
                owner_salary=salary_year,
                tax=tax,
                operating_cash_flow=y.cash_flow.operating,
                interest_added_back=p.interest,
                free_cash_flow=fcf,
                discount_factor=(1 / factor).quantize(Decimal("0.000001")),
                present_value=_round(fcf / factor),
            )
        )
    fcf = [y.free_cash_flow for y in years]
    first = years[0]
    sensitivity = Sensitivity(
        discount_rate_pct=[
            SensitivityCell(input=r, equity_value=_dcf(fcf, r, growth, net_debt).equity_value)
            for r in _steps(rate, (-RATE_STEP, Decimal(0), RATE_STEP), growth + 1, Decimal(50))
        ],
        terminal_growth_pct=[
            SensitivityCell(input=g, equity_value=_dcf(fcf, rate, g, net_debt).equity_value)
            for g in _steps(growth, GROWTH_STEPS, Decimal(-2), rate - 1)
        ],
        ebitda_multiple=[
            SensitivityCell(
                input=m,
                equity_value=_multiple(first.ebitda, first.revenue, m, net_debt).equity_value,
            )
            for m in _steps(
                multiple, (-MULTIPLE_STEP, Decimal(0), MULTIPLE_STEP), Decimal(1), Decimal(10)
            )
        ],
    )
    return CaseValuation(
        case=case.case,
        name=name,
        years=years,
        dcf=_dcf(fcf, rate, growth, net_debt),
        multiple=_multiple(first.ebitda, first.revenue, multiple, net_debt),
        sensitivity=sensitivity,
    )


def _inputs(v: ValueInputs, rate, growth, multiple, salary, as_of: date) -> list[ValuationInput]:
    def src(given, ours: str) -> str:
        return YOURS if given is not None else ours

    sheet = f"from the balance sheet at {as_of.isoformat()}"
    return [
        ValuationInput(
            key="discount_rate_pct", label="Discount rate", value=rate, unit="% a year",
            source=src(v.discount_rate_pct, f"{OURS}: typical for a small private firm"),
        ),
        ValuationInput(
            key="terminal_growth_pct", label="Growth after year 3", value=growth,
            unit="% a year", source=src(v.terminal_growth_pct, OURS),
        ),
        ValuationInput(
            key="ebitda_multiple", label="EBITDA multiple", value=multiple, unit="x year-1 EBITDA",
            source=src(
                v.ebitda_multiple,
                f"{OURS}: for a small private business, not a market quote or a price",
            ),
        ),
        ValuationInput(
            key="owner_salary_monthly", label="Owner's market salary deducted", value=salary,
            unit="S$ a month", source=src(v.owner_salary_monthly, "none deducted"),
        ),
        ValuationInput(
            key="tax_rate_pct", label="Income tax on positive operating profit",
            value=TAX_RATE, unit="%",
            source="Singapore headline corporate rate; partial exemption and past losses not "
            "applied, so slightly conservative",
        ),
        ValuationInput(
            key="net_debt", label="Net debt (loans + other borrowings - cash)", value=ZERO,
            unit="S$", source=sheet,
        ),
    ]  # fmt: skip


def business_value(
    store: Store,
    business_id: str,
    today: date,
    model_inputs: ModelInputs | None = None,
    inputs: ValueInputs | None = None,
) -> DomainResult[BusinessValue | None]:
    """Break-even per case and an estimated value. Value None with the reason when the
    business has no accrual books. Raises ValueError when growth after year 3 is not below
    the discount rate, or for an event outside the model's months."""
    inputs = inputs or ValueInputs()
    rate = DISCOUNT_RATE if inputs.discount_rate_pct is None else inputs.discount_rate_pct
    growth = TERMINAL_GROWTH if inputs.terminal_growth_pct is None else inputs.terminal_growth_pct
    multiple = EBITDA_MULTIPLE if inputs.ebitda_multiple is None else inputs.ebitda_multiple
    salary = ZERO if inputs.owner_salary_monthly is None else inputs.owner_salary_monthly
    if growth >= rate:
        raise ValueError(
            f"Growth after year 3 ({growth}%) must be below the discount rate ({rate}%)."
        )
    base = _base(store, business_id, today)
    if isinstance(base, str):
        return DomainResult(
            value=None,
            data_coverage=DataCoverage(period_start=today, period_end=today, record_count=0),
            warnings=[base],
        )
    built = model_from_base(store, business_id, base, model_inputs, include_monthly=True)
    model = built.value
    bs = base.opening.balance_sheet
    net_debt = bs.loans + bs.other_borrowings - bs.cash

    break_even = BreakEvenView(
        today_cash=_today_cash(store, business_id, today),
        today_accrual=_today_accrual(base),
        cases={
            c: _case_break_even(model.cases[c], CASE_NAMES[c], model.cases[c].cost_of_sales_pct)
            for c in CASES
        },
    )
    cases = {
        c: _case_valuation(model.cases[c], CASE_NAMES[c], rate, growth, multiple, salary, net_debt)
        for c in CASES
    }
    rows = _inputs(inputs, rate, growth, multiple, salary, bs.as_of)
    rows[-1] = rows[-1].model_copy(update={"value": net_debt})
    valuation = ValuationView(
        disclaimer=DISCLAIMER,
        inputs=rows,
        model_drivers=model.drivers,
        bridge=EquityBridge(
            as_of=bs.as_of,
            cash=bs.cash,
            loans=bs.loans,
            other_borrowings=bs.other_borrowings,
            net_debt=net_debt,
            loan_list=model.loans,
        ),
        book_equity=bs.total_equity,
        cases=cases,
    )

    warnings = [DISCLAIMER]
    for c in CASES:
        share = cases[c].dcf.terminal_share
        if share is not None and share > TERMINAL_SHARE_WARNING:
            warnings.append(
                f"{CASE_NAMES[c]} case: {share * 100:.0f}% of the DCF value comes after year 3, "
                "so it rests mostly on the business carrying on as projected."
            )
        ev = cases[c].dcf.enterprise_value
        if ev is not None and ev <= 0:
            warnings.append(f"{CASE_NAMES[c]} case: the DCF value is below zero on these figures.")
    if inputs.owner_salary_monthly is None:
        warnings.append(
            "No owner salary deducted: we can't tell whether payroll includes the owner. If the "
            "owner works unpaid, a buyer would deduct a market salary (give one to see the effect)."
        )
    warnings.append(
        "Tax is a flat 17% of positive operating profit (partial exemption and past losses not "
        "applied). Break-even and EBITDA are before tax."
    )
    warnings.extend(w for w in built.warnings if "Income tax" not in w)

    expected_be = break_even.cases["expected"]
    expected = cases["expected"]
    summary = [
        Driver(label="Expected case: break-even", detail=expected_be.status),
        Driver(
            label="Expected case: DCF equity value",
            amount=expected.dcf.equity_value,
            detail="" if expected.dcf.equity_value is not None else "not meaningful",
        ),
        Driver(
            label="Expected case: EBITDA multiple equity value",
            amount=expected.multiple.equity_value,
            detail="" if expected.multiple.equity_value is not None else "not meaningful",
        ),
        Driver(label="Book value of equity (accounting, not a price)", amount=bs.total_equity),
    ]
    return DomainResult(
        value=BusinessValue(
            starts_from=model.starts_from,
            first_month=model.first_month,
            last_month=model.last_month,
            break_even=break_even,
            valuation=valuation,
        ),
        drivers=summary,
        data_coverage=built.data_coverage,
        warnings=warnings,
    )
