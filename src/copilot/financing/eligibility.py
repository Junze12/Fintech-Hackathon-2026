"""Eligibility: facts about the business, and each product's rules checked against them in code.

Facts are company facts only (no personal characteristics of owners or staff; see
schemas.EligibilityMetric). Each fact says where it came from. A fact we can't establish is
"unknown", and an unknown rule makes the product not eligible ("can't verify"): we never
recommend a product the business might fail.
Pure functions over the store and sandbox: no writes, no LLM.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from copilot.analysis.metrics import period_metrics
from copilot.dates import add_months, months_window_start
from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    CopilotModel,
    DataCoverage,
    DocumentStatus,
    DomainResult,
    EligibilityMetric,
    EligibilityRule,
    FinancingProduct,
    Money,
    Operator,
    sgd,
)
from copilot.store import Store

M = EligibilityMetric
CENT = Decimal("0.01")
REVENUE_MONTHS = 12
BALANCE_MONTHS = 6
INVOICE_MAX_OVERDUE_DAYS = 90  # invoice financiers don't advance against older debts


class Fact(CopilotModel):
    metric: EligibilityMetric
    value: Decimal | bool | None  # None: unknown
    source: str


class BusinessFacts(CopilotModel):
    as_of: date
    facts: list[Fact]
    financeable_receivables: Money  # open invoices at most 90 days overdue

    def value(self, metric: EligibilityMetric) -> Decimal | bool | None:
        return next(f.value for f in self.facts if f.metric is metric)


class RuleResult(CopilotModel):
    description: str
    metric: EligibilityMetric
    status: Literal["pass", "fail", "unknown"]
    reason: str


class Eligibility(CopilotModel):
    product_id: str
    product_name: str
    lender: str
    eligible: bool
    rules: list[RuleResult]
    max_amount: Money  # the most this product could lend this business
    reasons: list[str]  # why not eligible (empty if eligible)


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day)


def business_facts(
    store: Store, sandbox: Sandbox, business_id: str, as_of: date | None = None
) -> DomainResult[BusinessFacts]:
    as_of = as_of or sandbox.today(business_id)
    business = store.get_business(business_id)
    txns = store.list_transactions(business_id, end=as_of)
    first_data = txns[0].date if txns else None

    window_start = months_window_start(as_of, REVENUE_MONTHS)
    full_year = first_data is not None and first_data <= window_start + timedelta(days=31)
    year = period_metrics(store, business_id, window_start, as_of).value if full_year else None

    month_ends = []
    end = as_of
    while len(month_ends) < BALANCE_MONTHS:
        last_of_month = add_months(date(end.year, end.month, 1), 1) - timedelta(days=1)
        if last_of_month <= as_of:
            month_ends.append(last_of_month)
        end = date(end.year, end.month, 1) - timedelta(days=1)
    enough_balance_history = first_data is not None and first_data <= min(month_ends)
    average_balance = (
        (
            sum(
                (sum(sandbox.balances(business_id, d).values(), Decimal("0")) for d in month_ends),
                Decimal("0"),
            )
            / BALANCE_MONTHS
        ).quantize(CENT)
        if enough_balance_history
        else None
    )

    financeable = sum(
        (
            i.amount - i.amount_paid
            for i in store.list_invoices(business_id, DocumentStatus.OPEN)
            if (as_of - i.due_date).days <= INVOICE_MAX_OVERDUE_DAYS
        ),
        Decimal("0"),
    )
    no_year = f"needs {REVENUE_MONTHS} months of bank data"
    facts = [
        Fact(
            metric=M.MONTHS_OPERATING,
            value=Decimal(_months_between(business.incorporated_on, as_of)),
            source=f"incorporated on {business.incorporated_on.isoformat()}",
        ),
        Fact(
            metric=M.ANNUAL_REVENUE,
            value=year.revenue if year else None,
            source=f"cash-basis sales receipts, {window_start.isoformat()} to {as_of.isoformat()}"
            if year
            else no_year,
        ),
        Fact(
            metric=M.GROSS_MARGIN,
            value=year.gross_margin if year else None,
            source="cash basis, last 12 months" if year else no_year,
        ),
        Fact(
            metric=M.AVERAGE_MONTHLY_BALANCE,
            value=average_balance,
            source=f"average of {BALANCE_MONTHS} month-end balances to {month_ends[0].isoformat()}"
            if average_balance is not None
            else f"needs {BALANCE_MONTHS} months of bank data",
        ),
        Fact(
            metric=M.EMPLOYEE_COUNT,
            value=Decimal(business.employee_count),
            source="business profile",
        ),
        Fact(
            metric=M.LOCAL_SHAREHOLDING_PCT,
            value=business.local_shareholding_pct,
            source="business profile",
        ),
        Fact(metric=M.REGISTERED_IN_SG, value=business.registered_in_sg, source="business profile"),
    ]
    return DomainResult[BusinessFacts](
        value=BusinessFacts(as_of=as_of, facts=facts, financeable_receivables=financeable),
        data_coverage=DataCoverage(
            period_start=first_data or as_of, period_end=as_of, record_count=len(txns)
        ),
        warnings=[f"{f.metric.value}: unknown ({f.source})" for f in facts if f.value is None],
    )


def show(metric: EligibilityMetric, value: Decimal | bool) -> str:
    """A fact or threshold in plain words."""
    if metric is M.REGISTERED_IN_SG:
        return "registered in Singapore" if value else "not registered in Singapore"
    assert isinstance(value, Decimal)
    if metric in (M.ANNUAL_REVENUE, M.AVERAGE_MONTHLY_BALANCE):
        return sgd(value)
    if metric is M.GROSS_MARGIN:
        return f"{value:.1%}"
    if metric is M.LOCAL_SHAREHOLDING_PCT:
        return f"{value.normalize():f}%"
    if metric is M.MONTHS_OPERATING:
        return f"{value:f} months"
    return f"{value:f} staff"


_WORDS = {Operator.GE: "at least", Operator.LE: "at most", Operator.EQ: ""}
_LABELS = {
    M.MONTHS_OPERATING: "time operating",
    M.ANNUAL_REVENUE: "annual revenue",
    M.EMPLOYEE_COUNT: "employees",
    M.LOCAL_SHAREHOLDING_PCT: "local shareholding",
    M.GROSS_MARGIN: "gross margin",
    M.AVERAGE_MONTHLY_BALANCE: "average month-end balance",
    M.REGISTERED_IN_SG: "registration",
}


def check_rule(rule: EligibilityRule, facts: BusinessFacts) -> RuleResult:
    actual = facts.value(rule.metric)
    label = _LABELS[rule.metric]
    if actual is None:
        source = next(f.source for f in facts.facts if f.metric is rule.metric)
        return RuleResult(
            description=rule.description,
            metric=rule.metric,
            status="unknown",
            reason=f"can't verify {label} ({source})",
        )
    if rule.operator is Operator.GE:
        ok = actual >= rule.threshold  # type: ignore[operator]
    elif rule.operator is Operator.LE:
        ok = actual <= rule.threshold  # type: ignore[operator]
    else:
        ok = actual == rule.threshold
    need = (
        show(rule.metric, rule.threshold)
        if rule.metric is M.REGISTERED_IN_SG
        else f"{_WORDS[rule.operator]} {show(rule.metric, rule.threshold)}"
    )
    return RuleResult(
        description=rule.description,
        metric=rule.metric,
        status="pass" if ok else "fail",
        reason=f"{label}: {show(rule.metric, actual)}; needs {need}",
    )


def check(product: FinancingProduct, facts: BusinessFacts) -> Eligibility:
    """Every rule of one product against the facts. Unknown counts as not eligible."""
    results = [check_rule(r, facts) for r in product.eligibility_rules]
    reasons = [r.reason for r in results if r.status != "pass"]
    max_amount = product.max_amount
    if product.advance_rate_pct is not None:
        cap = (facts.financeable_receivables * product.advance_rate_pct / 100).quantize(CENT)
        max_amount = min(max_amount, cap)
        if cap < product.min_amount:
            reasons.append(
                f"advances up to {product.advance_rate_pct.normalize():f}% of open invoices "
                f"({sgd(cap)}), below its minimum of {sgd(product.min_amount)}"
            )
    return Eligibility(
        product_id=product.id,
        product_name=product.name,
        lender=product.lender,
        eligible=not reasons,
        rules=results,
        max_amount=max_amount,
        reasons=reasons,
    )
