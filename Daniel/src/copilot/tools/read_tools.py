"""Read-only tools: thin wrappers over the domain modules. Minimum role: viewer.

Every number in these results comes from a domain function; the LLM only explains them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from copilot.analysis.adjustments import open_months, relabel_candidates
from copilot.analysis.breakdown import expense_breakdown
from copilot.analysis.compare import compare_periods, top_movers
from copilot.analysis.health import ageing, break_even_sales, cash_trend, debt_service_cover
from copilot.analysis.metrics import (
    customer_concentration,
    period_metrics,
    runway,
    supplier_concentration,
    working_capital,
)
from copilot.analysis.statements import (
    PeriodKind,
    StatementKind,
    View,
    accrual_margins,
    describe_adjustment,
    financial_statements,
    only,
)
from copilot.cashflow.alerts import CashAlert, default_floor, evaluate_alerts
from copilot.cashflow.forecast import WEEKS, forecast_13_weeks
from copilot.cashflow.obligations import DEFAULT_WEEKS, obligations_calendar
from copilot.cashflow.position import cash_position
from copilot.cashflow.recommend import recommend_actions
from copilot.cashflow.scenarios import MAX_CHANGES, Change, what_if
from copilot.cashflow.summary import Granularity, cash_summary
from copilot.financing.application import ApplicationDraft, build_draft, need_for
from copilot.financing.catalogue import load_catalogue
from copilot.financing.costs import quote
from copilot.financing.eligibility import business_facts
from copilot.financing.needs import MAX_MONTHS, MAX_NEED
from copilot.financing.ranking import match_financing
from copilot.reconcile import unlinked_receipts
from copilot.schemas import (
    Bill,
    CopilotModel,
    DocumentStatus,
    DomainResult,
    FinancingApplication,
    Id,
    Invoice,
    Money,
    PositiveMoney,
    Reminder,
    Role,
    UntrustedText,
    mask,
)
from copilot.tools.registry import Tool, ToolContext, ToolInput

# --- Inputs ------------------------------------------------------------------


class NoInput(ToolInput):
    pass


class GetMetricsInput(ToolInput):
    start: date = Field(description="First day of the period (YYYY-MM-DD), inclusive")
    end: date = Field(description="Last day of the period (YYYY-MM-DD), inclusive")

    @model_validator(mode="after")
    def _ordered(self) -> GetMetricsInput:
        if self.end < self.start:
            raise ValueError("end must not be before start")
        return self


class ComparePeriodsInput(GetMetricsInput):
    compare_start: date | None = Field(
        default=None,
        description=(
            "First day of the period to compare against (YYYY-MM-DD). Leave out, with "
            "compare_end, to use the period of the same length just before (e.g. September "
            "vs August, Q3 vs Q2)."
        ),
    )
    compare_end: date | None = Field(
        default=None, description="Last day of the period to compare against (YYYY-MM-DD)"
    )

    @model_validator(mode="after")
    def _compare_pair(self) -> ComparePeriodsInput:
        if (self.compare_start is None) != (self.compare_end is None):
            raise ValueError("give both compare_start and compare_end, or neither")
        if self.compare_start and self.compare_end and self.compare_end < self.compare_start:
            raise ValueError("compare_end must not be before compare_start")
        return self


class GetStatementsInput(ToolInput):
    period: PeriodKind = Field(
        default="month",
        description=(
            "month: one calendar month; quarter: the calendar quarter up to `month`; ytd: "
            "January up to `month`; last_12_months: the 12 months ending with `month`"
        ),
    )
    month: str | None = Field(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description=(
            "Last month of the period as YYYY-MM, e.g. 2026-09. Leave out for the latest "
            "complete month."
        ),
    )
    statement: StatementKind = Field(
        default="all",
        description=(
            "all, or just one: pnl (profit and loss), balance_sheet, cash_flow. Ask for one when "
            "the user asks about one."
        ),
    )
    view: View = Field(
        default="with_adjustments",
        description=(
            "with_adjustments (default): includes the owner's applied adjustments; as_imported: "
            "the books exactly as imported. Both ways, `adjustments` lists them with net profit "
            "as imported and with adjustments."
        ),
    )


class GetCashTrendInput(ToolInput):
    months: int = Field(
        default=12,
        ge=3,
        le=12,
        description="How many whole months to look back (3-12, default 12)",
    )


class GetAlertsInput(ToolInput):
    floor: Money | None = Field(
        default=None,
        description=(
            'Optional cash floor in SGD as a string, e.g. "20000.00", for this check only. '
            "Leave out to use the user's saved floor, or else the default: one month of "
            "recurring fixed costs."
        ),
    )


class GetObligationsInput(ToolInput):
    weeks: int = Field(
        default=DEFAULT_WEEKS,
        ge=1,
        le=WEEKS,
        description=f"How many weeks ahead to list (1-{WEEKS}, default {DEFAULT_WEEKS})",
    )


class GetCashSummaryInput(GetMetricsInput):
    granularity: Granularity = Field(
        default="month", description='"month" (default) or "week" (Monday to Sunday)'
    )


class RunWhatIfInput(ToolInput):
    changes: list[Change] = Field(
        min_length=1,
        max_length=MAX_CHANGES,
        description=(
            f"1-{MAX_CHANGES} changes to apply together. Each has a 'kind': "
            "collect_on_time {invoice_id}: invoice paid by its due date; "
            "delay_receipt {invoice_id OR customer_id, days}: money in arrives later; "
            "delay_payment {bill_id, days}: a bill is paid later; "
            'add_one_off {amount, date, label}: one extra payment (negative, e.g. "-20000.00") '
            "or receipt (positive); "
            "add_monthly {amount, start, label}: a new monthly cost (negative) or income, e.g. "
            "a new hire's total monthly cost including CPF; "
            "pause_recurring {category, until}: stop a recurring cost such as marketing until a "
            "date. Ids come from list_invoices / list_bills; dates are YYYY-MM-DD within the "
            "next 13 weeks."
        ),
    )


class RecommendActionsInput(ToolInput):
    buffer: Money = Field(
        default=Decimal("0"),
        ge=0,
        description=(
            'Optional cash cushion in SGD as a string, e.g. "10000.00". Gaps are measured '
            "below zero plus this buffer. Default 0."
        ),
    )


Purpose = Annotated[str, Field(max_length=140)]


class FindFinancingInput(ToolInput):
    amount: PositiveMoney | None = Field(
        default=None,
        le=MAX_NEED,
        description=(
            'Amount the user says they need, in SGD as a string, e.g. "50000.00". Leave out '
            "to use the forecast's funding need (after steps without borrowing)."
        ),
    )
    months: int | None = Field(
        default=None,
        ge=1,
        le=MAX_MONTHS,
        description="How many months the user needs it for. Leave out to use the forecast's.",
    )
    purpose: Purpose | None = Field(
        default=None, description="What the money is for, in the user's words (optional)"
    )


class ListDocumentsInput(ToolInput):
    status: Literal["open", "paid", "all"] = Field(
        default="open", description="Which documents to list. Default: open (unpaid) ones."
    )


# --- Views -------------------------------------------------------------------


class PayeeView(CopilotModel):
    id: Id
    name: UntrustedText
    bank_name: UntrustedText
    account: str  # masked, e.g. ••••9144
    allowlisted: bool
    verified: bool
    details_changed: bool


class DocumentView(CopilotModel):
    id: Id
    number: UntrustedText
    counterparty_id: Id
    counterparty_name: UntrustedText
    issue_date: date
    due_date: date
    amount: Money
    outstanding: Money
    status: DocumentStatus
    notes: UntrustedText | None = None


class ReceiptView(CopilotModel):
    transaction_id: Id
    date: date
    amount: Money
    customer_id: Id
    customer_name: UntrustedText
    description: UntrustedText


# --- Handlers ----------------------------------------------------------------


def _get_metrics(ctx: ToolContext, args: GetMetricsInput) -> dict:
    period = (ctx.store, ctx.business_id, args.start, args.end)
    today = ctx.sandbox.today(ctx.business_id)
    margins, why_not = accrual_margins(*period, today)
    return {
        "period": period_metrics(*period),
        "accrual": margins if margins is not None else {"unavailable": why_not},
        "working_capital": working_capital(*period, sandbox=ctx.sandbox),
        "concentration": customer_concentration(*period),
        "supplier_concentration": supplier_concentration(*period),
        "runway": runway(ctx.store, ctx.sandbox, ctx.business_id),
    }


def _get_financial_statements(ctx: ToolContext, args: GetStatementsInput):
    today = ctx.sandbox.today(ctx.business_id)
    result = financial_statements(
        ctx.store, ctx.business_id, today, args.period, args.month, view=args.view
    )
    if result.value is None:
        return result
    return result.model_copy(update={"value": only(result.value, args.statement)})


def _get_ageing(ctx: ToolContext, args: NoInput) -> dict:
    today = ctx.sandbox.today(ctx.business_id)
    return {
        "receivables": ageing(ctx.store, ctx.business_id, today, "receivables"),
        "payables": ageing(ctx.store, ctx.business_id, today, "payables"),
    }


def _get_cash_trend(ctx: ToolContext, args: GetCashTrendInput):
    return cash_trend(ctx.store, ctx.business_id, ctx.sandbox.today(ctx.business_id), args.months)


def _get_health_ratios(ctx: ToolContext, args: NoInput) -> dict:
    today = ctx.sandbox.today(ctx.business_id)
    return {
        "debt_service_cover": debt_service_cover(ctx.store, ctx.business_id, today),
        "break_even": break_even_sales(ctx.store, ctx.business_id, today),
    }


def _compare_args(ctx: ToolContext, args: ComparePeriodsInput) -> tuple:
    return (
        ctx.store,
        ctx.business_id,
        args.start,
        args.end,
        args.compare_start,
        args.compare_end,
    )


def _compare_periods(ctx: ToolContext, args: ComparePeriodsInput) -> dict:
    return {
        "comparison": compare_periods(*_compare_args(ctx, args)),
        "movers": top_movers(*_compare_args(ctx, args)),
    }


def _get_expense_breakdown(ctx: ToolContext, args: ComparePeriodsInput):
    return expense_breakdown(*_compare_args(ctx, args))


def _get_cash_position(ctx: ToolContext, args: NoInput):
    return cash_position(ctx.store, ctx.sandbox, ctx.business_id)


def _forecast_balance(ctx: ToolContext, args: NoInput):
    result = forecast_13_weeks(ctx.store, ctx.sandbox, ctx.business_id)
    if not result.value.saved_assumptions:
        return result
    imported = forecast_13_weeks(ctx.store, ctx.sandbox, ctx.business_id, use_saved=False)
    value = result.value.model_copy(update={"low_point_without_saved": imported.value.low_point})
    return result.model_copy(update={"value": value})


class AdjustmentView(CopilotModel):
    id: Id
    kind: str
    month: str
    status: str
    description: str  # built by code
    reason: UntrustedText  # typed by a user
    created_by: str
    applied_by: str | None
    undone_by: str | None


class AssumptionView(CopilotModel):
    id: Id
    kind: str
    status: str
    customer: UntrustedText | None
    days: int | None
    category: str | None
    monthly_amount: Money | None
    start: date | None
    reason: UntrustedText
    created_by: str


def _list_adjustments(ctx: ToolContext, args: NoInput) -> dict:
    today = ctx.sandbox.today(ctx.business_id)
    months, why_closed = open_months(ctx.store, ctx.business_id, today)
    names = {c.id: c.name for c in ctx.store.list_counterparties(ctx.business_id)}
    return {
        "open_months": months if months else {"none": why_closed},
        "adjustments": [
            AdjustmentView(
                id=a.id,
                kind=a.kind,
                month=a.month,
                status=a.status,
                description=describe_adjustment(ctx.store, a),
                reason=a.reason,
                created_by=a.created_by,
                applied_by=a.applied_by,
                undone_by=a.undone_by,
            )
            for a in ctx.store.list_adjustments(ctx.business_id)
        ],
        "saved_assumptions": [
            AssumptionView(
                id=a.id,
                kind=a.kind,
                status=a.status,
                customer=names.get(a.counterparty_id or "") if a.counterparty_id else None,
                days=a.days,
                category=a.category.value if a.category else None,
                monthly_amount=a.amount,
                start=a.start,
                reason=a.reason,
                created_by=a.created_by,
            )
            for a in ctx.store.list_assumptions(ctx.business_id)
        ],
        "uncategorised_payments": relabel_candidates(ctx.store, ctx.business_id, months),
    }


def resolve_floor(ctx: ToolContext, override: Decimal | None = None) -> tuple[Decimal, str]:
    """The cash floor to check against, and where it came from.

    Precedence: a floor given for this one check > the user's saved floor > the default.
    """
    if override is not None:
        return override, "this request"
    saved = ctx.store.get_alert_floor(ctx.business_id, ctx.user_id) if ctx.user_id else None
    if saved is not None:
        return saved, "your saved floor"
    today = ctx.sandbox.today(ctx.business_id)
    return default_floor(ctx.store, ctx.business_id, today).value, "default"


def ranked_alerts(
    ctx: ToolContext, floor_override: Decimal | None = None
) -> DomainResult[list[CashAlert]]:
    floor, _ = resolve_floor(ctx, floor_override)
    forecast = forecast_13_weeks(ctx.store, ctx.sandbox, ctx.business_id)
    return evaluate_alerts(ctx.store, ctx.business_id, forecast, floor)


def _get_alerts(ctx: ToolContext, args: GetAlertsInput) -> dict:
    floor, source = resolve_floor(ctx, args.floor)
    return {
        "floor": floor,
        "floor_source": source,
        "alerts": ranked_alerts(ctx, args.floor),
    }


def _get_obligations(ctx: ToolContext, args: GetObligationsInput):
    forecast = forecast_13_weeks(ctx.store, ctx.sandbox, ctx.business_id)
    return obligations_calendar(forecast, args.weeks)


def _get_cash_summary(ctx: ToolContext, args: GetCashSummaryInput):
    return cash_summary(ctx.store, ctx.business_id, args.start, args.end, args.granularity)


def _run_what_if(ctx: ToolContext, args: RunWhatIfInput):
    forecast = forecast_13_weeks(ctx.store, ctx.sandbox, ctx.business_id)
    return what_if(ctx.store, ctx.business_id, forecast, list(args.changes))


def _recommend_actions(ctx: ToolContext, args: RecommendActionsInput):
    forecast = forecast_13_weeks(ctx.store, ctx.sandbox, ctx.business_id)
    return recommend_actions(ctx.store, ctx.business_id, forecast, args.buffer)


def _find_financing(ctx: ToolContext, args: FindFinancingInput):
    forecast = forecast_13_weeks(ctx.store, ctx.sandbox, ctx.business_id)
    return match_financing(
        ctx.store,
        ctx.sandbox,
        ctx.business_id,
        forecast,
        amount=args.amount,
        months=args.months,
        purpose=args.purpose,
    )


def application_view(ctx: ToolContext, app: FinancingApplication) -> ApplicationDraft:
    """An application as the user sees it, priced the same way as when it was pre-filled."""
    product = load_catalogue().get(app.product_id)
    if product is None:
        raise ValueError(f"product {app.product_id} is no longer in the catalogue")
    facts = business_facts(ctx.store, ctx.sandbox, ctx.business_id).value.facts
    business = ctx.store.get_business(ctx.business_id)
    return build_draft(app, business, quote(product, need_for(app)), facts)


def _list_applications(ctx: ToolContext, args: NoInput) -> list[ApplicationDraft]:
    return [application_view(ctx, a) for a in ctx.store.list_applications(ctx.business_id)]


def _list_payees(ctx: ToolContext, args: NoInput) -> list[PayeeView]:
    return [
        PayeeView(
            id=p.id,
            name=p.name,
            bank_name=p.bank_name,
            account=mask(p.account_number),
            allowlisted=p.allowlisted,
            verified=p.verified,
            details_changed=p.details_changed_at is not None,
        )
        for p in ctx.store.list_payees(ctx.business_id)
    ]


def _views(ctx: ToolContext, docs: list[Invoice] | list[Bill]) -> list[DocumentView]:
    names = {c.id: c.name for c in ctx.store.list_counterparties(ctx.business_id)}
    return [
        DocumentView(
            id=d.id,
            number=d.number,
            counterparty_id=d.counterparty_id,
            counterparty_name=names.get(d.counterparty_id, d.counterparty_id),
            issue_date=d.issue_date,
            due_date=d.due_date,
            amount=d.amount,
            outstanding=d.amount - d.amount_paid,
            status=d.status,
            notes=d.notes,
        )
        for d in docs
    ]


def _status(args: ListDocumentsInput) -> DocumentStatus | None:
    return None if args.status == "all" else DocumentStatus(args.status)


def _list_bills(ctx: ToolContext, args: ListDocumentsInput) -> list[DocumentView]:
    return _views(ctx, ctx.store.list_bills(ctx.business_id, _status(args)))


def _list_invoices(ctx: ToolContext, args: ListDocumentsInput) -> list[DocumentView]:
    return _views(ctx, ctx.store.list_invoices(ctx.business_id, _status(args)))


def _list_receipts(ctx: ToolContext, args: NoInput) -> list[ReceiptView]:
    names = {c.id: c.name for c in ctx.store.list_counterparties(ctx.business_id)}
    return [
        ReceiptView(
            transaction_id=t.id,
            date=t.date,
            amount=t.amount,
            customer_id=t.counterparty_id or "",
            customer_name=names.get(t.counterparty_id or "", ""),
            description=t.description,
        )
        for t in unlinked_receipts(ctx.store, ctx.business_id)
    ]


def _list_reminders(ctx: ToolContext, args: NoInput) -> list[Reminder]:
    return ctx.store.list_reminders(ctx.business_id)


# --- Definitions -------------------------------------------------------------

READ_TOOLS = [
    Tool(
        name="get_metrics",
        description=(
            "Business performance for a period: revenue, cost of goods sold, operating "
            "expenses, gross and operating margin, net cash flow (cash basis); accrual revenue "
            "and gross, operating and net margin when the books allow (whole months only; "
            "lead with these for 'how profitable are we?', cash margins answer 'how much cash "
            "did trading bring in?'); DSO, DPO, "
            "cash conversion cycle, net working capital (cash at period end + receivables - "
            "payables), the largest customer's share of invoiced sales and the largest "
            "supplier's share of bills (invoice basis); plus current runway in months. Use for "
            "'how did we do last quarter?', 'what's our DSO?', 'what's our working capital?' "
            "or 'how dependent are we on our biggest customer or supplier?'. Returns {period, "
            "accrual, working_capital, concentration, supplier_concentration, runway}, each "
            "with value, drivers, data_coverage and warnings. Always say which basis a number uses."
        ),
        input_model=GetMetricsInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_metrics,
    ),
    Tool(
        name="get_financial_statements",
        description=(
            "The three financial statements on accrual basis (sales and costs counted when "
            "invoiced or incurred, amounts excluding GST), built from the books and checked: "
            "pnl (revenue, cost of sales, gross profit, operating expenses by line incl. payroll "
            "and depreciation, operating profit, interest, net profit); balance_sheet at the "
            "period's last month-end (cash = the bank, receivables, stock, fixed assets, "
            "payables, GST and CPF owed, loan split into due within / after 12 months, equity); "
            "cash_flow (net profit + depreciation + working-capital changes = operating cash; "
            "loan principal = financing; opening and closing cash). Also ratios (gross, "
            "operating and net margin and debt ratio as fractions: show them as percentages, "
            "e.g. 0.4937 -> 49.37%; EBITDA; current ratio in times), checks "
            "(balanced, cash_matches_bank), the fixed-asset and loan list. Use for 'did we make "
            "a profit?', 'show me the P&L / balance sheet / cash flow', 'what do we own and "
            "owe?', 'why is profit different from cash?'. Returns value None with the reason "
            "if the business has no opening balance sheet: then say so and offer cash-basis "
            "figures. When `adjustments` is present, say the figures include the owner's "
            "adjustments, give net profit as imported and with adjustments, and list them."
        ),
        input_model=GetStatementsInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_financial_statements,
    ),
    Tool(
        name="get_ageing",
        description=(
            "Unpaid customer invoices (receivables) and supplier bills (payables) as of today, "
            "grouped by how overdue they are: not yet due, 1-30, 31-60, 61-90, over 90 days. "
            "Receivables also list each customer's habit: average days they pay after the due "
            "date (from matched receipts), what they owe and how much is overdue, slowest "
            "payer first. Invoice basis. Use for 'who owes us money?', 'who pays late?', "
            "'how old are our receivables?' or 'which bills are overdue?'. Returns "
            "{receivables, payables}."
        ),
        input_model=NoInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_ageing,
    ),
    Tool(
        name="get_cash_trend",
        description=(
            "Month-by-month revenue, money out (gross burn) and net cash flow over the last "
            "whole months (default 12), with month-on-month revenue growth, averages for the "
            "last 3 months vs the 3 before, net burn, revenue volatility (std dev / mean of "
            "monthly revenue) and a direction: improving, worsening or steady. Cash basis. "
            "Use for 'are we getting better or worse?', 'how fast are we burning cash?' or "
            "'how steady are our sales?'."
        ),
        input_model=GetCashTrendInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_cash_trend,
    ),
    Tool(
        name="get_health_ratios",
        description=(
            "Two lender-style checks as of today, cash basis. debt_service_cover: money left "
            "after running the business (sales minus operating costs, tax and owner drawings) "
            "over the last 12 whole months, divided by loan repayments; below 1.0 means "
            "repayments weren't covered (null when there are no loan repayments). break_even: "
            "monthly sales needed to cover fixed operating costs at the last 3 months' gross "
            "margin, compared with actual average monthly sales (headroom). Use for 'can we "
            "afford our loan?', 'what would a bank think?' or 'how much do we need to sell to "
            "break even?'. Returns {debt_service_cover, break_even}."
        ),
        input_model=NoInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_health_ratios,
    ),
    Tool(
        name="compare_periods",
        description=(
            "Compare a period with an earlier one (default: the same length just before). "
            "Returns {comparison, movers}: comparison has each metric before, after and "
            "change (revenue, costs, margins, net cash flow on cash basis; DSO, DPO, cash "
            "conversion cycle on invoice basis); movers are the categories whose cash flow "
            "changed most, each with the counterparties behind the change and a note such as "
            "'only in the previous period' or '3 receipts vs 1'. Use for 'how did September "
            "compare with August?' or 'why did revenue drop?'."
        ),
        input_model=ComparePeriodsInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_compare_periods,
    ),
    Tool(
        name="get_expense_breakdown",
        description=(
            "Spending by category for a period (cash basis, transfers between own accounts "
            "left out): amount, share of total spend, group (cogs, opex, financing, "
            "non-operating) and change from an earlier period (default: the same length just "
            "before), flagging new and stopped categories. Use for 'break down our expenses' "
            "or 'what are we spending the most on?'."
        ),
        input_model=ComparePeriodsInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_expense_breakdown,
    ),
    Tool(
        name="get_cash_position",
        description=(
            "Current balance of each bank account and the total, as of today. "
            "Use for 'how much cash do we have?'. Account ids returned here are the ones "
            "schedule_payment needs."
        ),
        input_model=NoInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_cash_position,
    ),
    Tool(
        name="forecast_balance",
        description=(
            "13-week cash forecast from today: weekly inflows, outflows and balances, the low "
            "point (date and amount), the items behind it and the assumptions used. Use for "
            "'will we run out of cash?' or 'what does next month look like?'. If the owner has "
            "saved assumptions, they are listed in saved_assumptions and "
            "low_point_without_saved gives the low point from the imported data alone: "
            "mention both."
        ),
        input_model=NoInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_forecast_balance,
    ),
    Tool(
        name="get_alerts",
        description=(
            "Cash alerts, most important first: cash falling below the floor in the next 13 "
            "weeks (threshold), a payment the business can't cover (shortfall) and customer "
            "invoices past due (overdue_receivable, compared with that customer's usual "
            "delay). Each alert has severity, message, SGD impact, date and drivers. Also "
            "returns the floor used and where it came from. Use at the start of a session "
            "and for 'anything I should worry about?'."
        ),
        input_model=GetAlertsInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_alerts,
    ),
    Tool(
        name="get_obligations",
        description=(
            "Calendar of known money in and out over the next few weeks: payments the owner "
            "scheduled, open bills (on their due date), recurring costs such as rent and "
            "payroll, and expected customer payments on open invoices. Each row has date, "
            "amount, how certain it is and the forecast balance at the end of that day. Use "
            "for 'what's coming up?' or 'what do we have to pay this month?'."
        ),
        input_model=GetObligationsInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_obligations,
    ),
    Tool(
        name="get_cash_summary",
        description=(
            "Money in and out of the bank accounts by category (sales, payroll, rent, ...) for "
            "each month or week of a past period, with net cash flow and totals. Transfers "
            "between the business's own accounts are left out. Use for 'where did our money "
            "go last quarter?' or 'what came in and out in August?'."
        ),
        input_model=GetCashSummaryInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_get_cash_summary,
    ),
    Tool(
        name="run_what_if",
        description=(
            "Re-run the 13-week forecast with hypothetical changes (a customer paying late, a "
            "bill paid later, a one-off purchase, a new hire, pausing a cost) and compare with "
            "the current forecast: low point before and after, first day below zero, week-by-"
            "week difference and what moved. Nothing is changed for real. Use for 'what if "
            "Bayfront pays 3 weeks late?' or 'can we afford a new hire at S$5,000 a month?'. "
            "To correct a scenario, call it again with the updated changes."
        ),
        input_model=RunWhatIfInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_run_what_if,
    ),
    Tool(
        name="recommend_actions",
        description=(
            "Ways to close a forecast cash gap, most preferred first: collect receivables, "
            "reschedule supplier bills, pause discretionary spending, and only then borrow. "
            "Each option shows which gaps it closes and its assumption. Returns the plan "
            "(options that together help most), whether borrowing is needed, and if so the "
            "funding need: amount, draw date, repay date and duration. Say plainly when "
            "borrowing is not needed. Use for 'what should I do about the cash gap?' or 'do I "
            "need a loan?'."
        ),
        input_model=RecommendActionsInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_recommend_actions,
    ),
    Tool(
        name="find_financing",
        description=(
            "Financing options for the business. Uses the forecast's funding need (after "
            "steps without borrowing) unless the user states an amount and/or months. Returns "
            "the need, the business facts used, eligibility for EVERY product with reasons, "
            "and eligible products ranked: those that keep cash above zero first, then by "
            "total S$ cost. Each has amount, term, effective annual rate (EIR), total cost and "
            "flags. Always tell the user the total cost and EIR, never say or imply a loan "
            "will be approved, never suggest a product marked not eligible, and say plainly "
            "when borrowing is not needed. Use for 'what are my financing options?' or "
            "'I need S$50k for 6 months'."
        ),
        input_model=FindFinancingInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_find_financing,
    ),
    Tool(
        name="list_applications",
        description=(
            "Financing applications saved for the business (drafts and submitted ones) with "
            "product, amount, term, EIR, total cost and status. Use to find the "
            "application_id for submit_application."
        ),
        input_model=NoInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_list_applications,
    ),
    Tool(
        name="list_payees",
        description=(
            "Payees the business can pay, with masked account numbers and whether each is "
            "allowlisted and verified. Only allowlisted, verified payees with unchanged bank "
            "details can be paid. Use to find the payee_id for schedule_payment."
        ),
        input_model=NoInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_list_payees,
    ),
    Tool(
        name="list_bills",
        description=(
            "Supplier bills (money the business owes): number, supplier, due date, amount and "
            "outstanding balance. Use to find the bill_id for schedule_payment."
        ),
        input_model=ListDocumentsInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_list_bills,
    ),
    Tool(
        name="list_invoices",
        description=(
            "Customer invoices (money owed to the business): number, customer, due date, "
            "amount and outstanding balance. Use to find overdue invoices and the invoice_id "
            "for draft_reminder."
        ),
        input_model=ListDocumentsInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_list_invoices,
    ),
    Tool(
        name="list_receipts",
        description=(
            "Money received from customers that is not yet recorded against any invoice: date, "
            "amount, customer and bank description. Use to find the transaction_id for "
            "mark_invoice_paid."
        ),
        input_model=NoInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_list_receipts,
    ),
    Tool(
        name="list_adjustments",
        description=(
            "The owner's recorded adjustments to the books (drafts, applied, undone) and saved "
            "forecast assumptions (active, removed), with who made them; the months that can "
            "still be adjusted; and uncategorised payments in those months (transaction ids "
            "for a relabel). Use for 'what adjustments are there?', 'what assumptions are we "
            "using?', or to find an adjustment_id / assumption_id / transaction_id."
        ),
        input_model=NoInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_list_adjustments,
    ),
    Tool(
        name="list_reminders",
        description=(
            "Payment reminders for customer invoices: drafts and sent ones, with their text. "
            "Use to find the reminder_id for send_reminder."
        ),
        input_model=NoInput,
        min_role=Role.VIEWER,
        kind="read",
        run=_list_reminders,
    ),
]
