"""Business financial metrics. Cash basis in v1 (accrual basis is deferred)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from copilot.dates import months_window_start
from copilot.reconcile import match_settlements, outstanding_at
from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    Bill,
    CategoryGroup,
    CopilotModel,
    DataCoverage,
    DocumentStatus,
    DomainResult,
    Driver,
    Id,
    Invoice,
    Money,
    UntrustedText,
    sgd,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

RATIO = Decimal("0.0001")
CENT = Decimal("0.01")
RUNWAY_MONTHS = 3


class PeriodMetrics(CopilotModel):
    start: date
    end: date
    basis: Literal["cash"] = "cash"
    revenue: Money
    cogs: Money  # positive number = cost
    opex: Money  # positive number = cost
    gross_margin: Decimal | None  # fraction, e.g. 0.3512 = 35.12%
    operating_margin: Decimal | None
    net_cash_flow: Money  # all money in minus out, excluding own-account transfers
    uncategorised_count: int
    uncategorised_net: Money


def period_metrics(
    store: Store, business_id: str, start: date, end: date
) -> DomainResult[PeriodMetrics]:
    txns = store.list_transactions(business_id, start=start, end=end)
    totals = dict.fromkeys(CategoryGroup, Decimal("0"))
    net = Decimal("0")
    for t in txns:
        totals[t.category.group] += t.amount
        if t.category is not Cat.TRANSFER:
            net += t.amount

    revenue = totals[CategoryGroup.REVENUE]
    cogs = -totals[CategoryGroup.COGS]
    opex = -totals[CategoryGroup.OPEX]
    uncategorised = [t for t in txns if t.category is Cat.UNCATEGORISED]

    warnings = ["Cash basis: revenue and costs are counted when money moves, not when invoiced"]
    if revenue > 0:
        gross = ((revenue - cogs) / revenue).quantize(RATIO)
        operating = ((revenue - cogs - opex) / revenue).quantize(RATIO)
    else:
        gross = operating = None
        warnings.append("No revenue in this period, so margins can't be calculated")
    if uncategorised:
        warnings.append(
            f"{len(uncategorised)} uncategorised transactions "
            f"(net {sgd(sum(t.amount for t in uncategorised))}) are excluded from revenue and costs"
        )
    if not txns:
        warnings.append("No transactions in this period")

    return DomainResult[PeriodMetrics](
        value=PeriodMetrics(
            start=start,
            end=end,
            revenue=revenue,
            cogs=cogs,
            opex=opex,
            gross_margin=gross,
            operating_margin=operating,
            net_cash_flow=net,
            uncategorised_count=len(uncategorised),
            uncategorised_net=sum((t.amount for t in uncategorised), Decimal("0")),
        ),
        drivers=[
            Driver(label="Revenue (sales received)", amount=revenue),
            Driver(label="Cost of goods sold", amount=-cogs),
            Driver(label="Operating expenses", amount=-opex),
        ],
        data_coverage=DataCoverage(period_start=start, period_end=end, record_count=len(txns)),
        warnings=warnings,
    )


class Runway(CopilotModel):
    as_of: date
    cash: Money
    avg_monthly_net_flow: Money
    months: Decimal | None  # None when the business is not burning cash
    status: Literal["cash-flow positive", "burning cash"]


def runway(
    store: Store, sandbox: Sandbox, business_id: str, as_of: date | None = None
) -> DomainResult[Runway]:
    """Months of cash left at the recent burn rate (only when net outflow > 0)."""
    as_of = as_of or sandbox.today(business_id)
    start = months_window_start(as_of, RUNWAY_MONTHS)
    cash = sum(sandbox.balances(business_id, as_of).values(), Decimal("0"))
    txns = store.list_transactions(business_id, start=start, end=as_of)
    net = sum((t.amount for t in txns if t.category is not Cat.TRANSFER), Decimal("0"))
    avg = (net / RUNWAY_MONTHS).quantize(CENT)

    warnings = []
    if avg >= 0:
        months, status = None, "cash-flow positive"
    else:
        months = max(Decimal("0"), cash / -avg).quantize(Decimal("0.1"))
        status = "burning cash"
        if cash <= 0:
            warnings.append("Cash is already at or below zero")
    first = store.list_transactions(business_id, end=as_of)[:1]
    if first and first[0].date > start:
        warnings.append(
            f"Less than {RUNWAY_MONTHS} months of history; burn rate is based on a shorter period"
        )

    return DomainResult[Runway](
        value=Runway(
            as_of=as_of, cash=cash, avg_monthly_net_flow=avg, months=months, status=status
        ),
        drivers=[
            Driver(label="Cash across all accounts", amount=cash),
            Driver(label=f"Average monthly net cash flow, last {RUNWAY_MONTHS} months", amount=avg),
        ],
        data_coverage=DataCoverage(period_start=start, period_end=as_of, record_count=len(txns)),
        warnings=warnings,
    )


# --- Working capital and concentration (invoice basis) ---------------------------------------
# Receivables and payables only exist on invoices and bills, so these metrics are invoice-based
# (agreed 2026-10-05): DSO and concentration use invoiced sales, DPO uses bills received. Revenue
# and margins above stay cash basis. Every result says which basis it used.

DAYS = Decimal("0.1")
CONCENTRATION_WARNING = Decimal("0.5")


class WorkingCapital(CopilotModel):
    start: date
    end: date
    basis: Literal["invoice"] = "invoice"
    days: int
    invoiced_sales: Money  # invoices issued in the period
    receivables: Money  # unpaid customer invoices at the end of the period
    dso: Decimal | None  # days sales outstanding
    bills_received: Money  # supplier bills issued in the period
    payables: Money  # unpaid supplier bills at the end of the period
    dpo: Decimal | None  # days payables outstanding
    ccc: Decimal | None  # cash conversion cycle = DSO - DPO (no DIO: no inventory data)
    cash: Money | None = None  # bank balance at period end (only when a sandbox is given)
    net_working_capital: Money | None = None  # cash + receivables - payables


def working_capital(
    store: Store, business_id: str, start: date, end: date, sandbox: Sandbox | None = None
) -> DomainResult[WorkingCapital]:
    """DSO, DPO and cash conversion cycle; with `sandbox`, also net working capital."""
    days = (end - start).days + 1
    invoices = store.list_invoices(business_id)
    bills = store.list_bills(business_id)
    sales = sum((i.amount for i in invoices if start <= i.issue_date <= end), Decimal("0"))
    purchases = sum((b.amount for b in bills if start <= b.issue_date <= end), Decimal("0"))
    open_invoices = [i for i in invoices if i.status is DocumentStatus.OPEN]
    open_bills = [b for b in bills if b.status is DocumentStatus.OPEN]
    ar = outstanding_at(open_invoices, match_settlements(store, business_id, "invoice"), end)
    ap = outstanding_at(open_bills, match_settlements(store, business_id, "bill"), end)

    warnings = [
        "Invoice basis: receivables, payables and their days use invoices and bills, "
        "not bank receipts",
        "DIO omitted: there is no inventory data, so the cash conversion cycle is DSO - DPO",
    ]
    dso = (ar.total / sales * days).quantize(DAYS) if sales > 0 else None
    dpo = (ap.total / purchases * days).quantize(DAYS) if purchases > 0 else None
    if dso is None:
        warnings.append("No invoices issued in this period, so DSO can't be calculated")
    if dpo is None:
        warnings.append("No supplier bills received in this period, so DPO can't be calculated")
    assumed = ar.assumed + ap.assumed
    if assumed:
        warnings.append(
            f"{len(assumed)} documents could not be matched to a bank transaction; their "
            "payment date was assumed (paid ones on the due date, part payments before "
            "period end)"
        )

    cash = nwc = None
    if sandbox is not None:
        cash = sum(sandbox.balances(business_id, end).values(), Decimal("0"))
        nwc = cash + ar.total - ap.total
        warnings.append(
            "Net working capital = cash at period end + receivables - payables; no inventory "
            "or other short-term debt is in the data"
        )

    names = {c.id: c.name for c in store.list_counterparties(business_id)}
    by_id = {d.id: d for d in [*invoices, *bills]}
    largest = sorted(ar.by_document.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    drivers = [
        Driver(label="Receivables at period end", amount=ar.total),
        Driver(label="Payables at period end", amount=-ap.total),
    ] + [
        Driver(
            label=f"Unpaid invoice {by_id[doc_id].number}",
            amount=amount,
            detail=(
                f"{names.get(by_id[doc_id].counterparty_id, by_id[doc_id].counterparty_id)}, "
                f"due {by_id[doc_id].due_date.isoformat()}"
            ),
        )
        for doc_id, amount in largest
    ]

    return DomainResult[WorkingCapital](
        value=WorkingCapital(
            start=start,
            end=end,
            days=days,
            invoiced_sales=sales,
            receivables=ar.total,
            dso=dso,
            bills_received=purchases,
            payables=ap.total,
            dpo=dpo,
            ccc=dso - dpo if dso is not None and dpo is not None else None,
            cash=cash,
            net_working_capital=nwc,
        ),
        drivers=drivers,
        data_coverage=DataCoverage(
            period_start=start, period_end=end, record_count=len(invoices) + len(bills)
        ),
        warnings=warnings,
    )


def _shares(
    docs: list[Invoice] | list[Bill], names: dict[str, str], start: date, end: date
) -> tuple[Decimal, list[tuple[str, str, Decimal, Decimal]]]:
    """Total and (id, name, amount, share) per counterparty for documents issued in the period,
    largest first."""
    totals: dict[str, Decimal] = {}
    for d in docs:
        if start <= d.issue_date <= end:
            totals[d.counterparty_id] = totals.get(d.counterparty_id, Decimal("0")) + d.amount
    total = sum(totals.values(), Decimal("0"))
    rows = [
        (cid, names.get(cid, cid), amount, (amount / total).quantize(RATIO))
        for cid, amount in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return total, rows


class CustomerShare(CopilotModel):
    customer_id: Id
    name: UntrustedText
    invoiced: Money
    share: Decimal  # fraction of all invoiced sales in the period


class Concentration(CopilotModel):
    start: date
    end: date
    basis: Literal["invoice"] = "invoice"
    total_invoiced: Money
    largest: CustomerShare | None
    customers: list[CustomerShare]  # largest first


def customer_concentration(
    store: Store, business_id: str, start: date, end: date
) -> DomainResult[Concentration]:
    """Largest customer's share of invoiced sales (invoices issued in the period)."""
    invoices = store.list_invoices(business_id)
    names = {c.id: c.name for c in store.list_counterparties(business_id)}
    total, rows = _shares(invoices, names, start, end)
    customers = [
        CustomerShare(customer_id=cid, name=name, invoiced=amount, share=share)
        for cid, name, amount, share in rows
    ]
    largest = customers[0] if customers else None

    warnings = ["Invoice basis: shares use invoices issued in the period, not bank receipts"]
    if largest is None:
        warnings.append("No invoices issued in this period, so concentration can't be measured")
    elif largest.share > CONCENTRATION_WARNING:
        warnings.append(
            f"One customer accounts for more than {CONCENTRATION_WARNING:.0%} of invoiced "
            "sales; losing or delaying them would hit cash hard"
        )
    return DomainResult[Concentration](
        value=Concentration(
            start=start,
            end=end,
            total_invoiced=total,
            largest=largest,
            customers=customers,
        ),
        drivers=[
            Driver(label=c.name, amount=c.invoiced, detail=f"{c.share:.1%} of invoiced sales")
            for c in customers[:3]
        ],
        data_coverage=DataCoverage(
            period_start=start,
            period_end=end,
            record_count=sum(1 for i in invoices if start <= i.issue_date <= end),
        ),
        warnings=warnings,
    )


class SupplierShare(CopilotModel):
    supplier_id: Id
    name: UntrustedText
    billed: Money
    share: Decimal  # fraction of all supplier bills received in the period


class SupplierConcentration(CopilotModel):
    start: date
    end: date
    basis: Literal["invoice"] = "invoice"
    total_billed: Money
    largest: SupplierShare | None
    suppliers: list[SupplierShare]  # largest first


def supplier_concentration(
    store: Store, business_id: str, start: date, end: date
) -> DomainResult[SupplierConcentration]:
    """Largest supplier's share of bills received in the period (dependence on one supplier)."""
    bills = store.list_bills(business_id)
    names = {c.id: c.name for c in store.list_counterparties(business_id)}
    total, rows = _shares(bills, names, start, end)
    suppliers = [
        SupplierShare(supplier_id=sid, name=name, billed=amount, share=share)
        for sid, name, amount, share in rows
    ]
    largest = suppliers[0] if suppliers else None

    warnings = ["Invoice basis: shares use supplier bills issued in the period, not payments"]
    if largest is None:
        warnings.append("No supplier bills in this period, so concentration can't be measured")
    elif largest.share > CONCENTRATION_WARNING:
        warnings.append(
            f"One supplier accounts for more than {CONCENTRATION_WARNING:.0%} of purchases; a "
            "price rise or delivery problem there would hit the business hard"
        )
    return DomainResult[SupplierConcentration](
        value=SupplierConcentration(
            start=start, end=end, total_billed=total, largest=largest, suppliers=suppliers
        ),
        drivers=[
            Driver(label=x.name, amount=x.billed, detail=f"{x.share:.1%} of supplier bills")
            for x in suppliers[:3]
        ],
        data_coverage=DataCoverage(
            period_start=start,
            period_end=end,
            record_count=sum(1 for b in bills if start <= b.issue_date <= end),
        ),
        warnings=warnings,
    )
