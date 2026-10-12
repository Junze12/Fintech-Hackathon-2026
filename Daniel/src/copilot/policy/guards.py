"""Policy guards for write actions. Each returns the reasons to refuse; empty means allowed.

Guards run twice: when the action is proposed, and again when the user confirms, because
the situation may have changed in between (e.g. another payment used up the daily limit).
A write tool with no guard registered here is refused (fail closed).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from copilot.analysis.adjustments import (
    ACCRUAL_LINES,
    MAX_ADJUSTMENT,
    MAX_APPLIED,
    MAX_DRAFTS,
    OPEN_MONTHS,
    RELABEL_FROM,
    RELABEL_TO,
    open_months,
    settled_bill_payments,
)
from copilot.cashflow.forecast import horizon_end
from copilot.cashflow.recurring import detect_recurring
from copilot.financing.application import need_for
from copilot.financing.catalogue import load_catalogue
from copilot.financing.costs import quote
from copilot.financing.eligibility import business_facts, check
from copilot.policy.limits import get_limits
from copilot.reconcile import match_settlements
from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    Adjustment,
    ApplicationStatus,
    BalanceLine,
    CounterpartyKind,
    DocumentStatus,
    PaymentStatus,
    ScheduledPayment,
    sgd,
)
from copilot.store import NotFoundError, Store
from copilot.tools.registry import ToolContext
from copilot.tools.write_tools import (
    MAX_ASSUMED_COST,
    MAX_ASSUMPTIONS,
    MAX_FLOOR,
    REMINDER_GAP_DAYS,
    AdjustmentIdInput,
    AssumptionIdInput,
    DraftAdjustmentInput,
    DraftReminderInput,
    MarkInvoicePaidInput,
    PrefillApplicationInput,
    SaveAssumptionInput,
    SchedulePaymentInput,
    SendReminderInput,
    SetCashFloorInput,
    SubmitApplicationInput,
    draft_from_args,
    prefill_match,
)

Guard = Callable[[Store, Sandbox, str, Any], list[str]]

# Payments that count towards the daily limit and against a bill's outstanding balance.
_COMMITTED = (PaymentStatus.SCHEDULED, PaymentStatus.EXECUTED)


def _same_name(a: str, b: str) -> bool:
    return " ".join(a.casefold().split()) == " ".join(b.casefold().split())


def check_scheduled_execution(
    store: Store, sandbox: Sandbox, business_id: str, payment: ScheduledPayment
) -> list[str]:
    """Run the payment guard again when a scheduled payment comes due (known risk R8).

    The payee may have been un-verified, its bank details changed, or the limits used up since
    the owner confirmed. The payment itself is already counted in the day's total and against
    the bill, so it is left out of those sums here, or it would always block itself.
    """
    req = SchedulePaymentInput(
        payee_id=payment.payee_id,
        from_account_id=payment.from_account_id,
        amount=payment.amount,
        pay_on=payment.pay_on,
        bill_id=payment.bill_id,
        reference=payment.reference,
    )
    return check_payment(store, sandbox, business_id, req, exclude_payment_id=payment.id)


def check_payment(
    store: Store,
    sandbox: Sandbox,
    business_id: str,
    req: SchedulePaymentInput,
    exclude_payment_id: str | None = None,
) -> list[str]:
    reasons: list[str] = []
    today = sandbox.today(business_id)

    # Payee: the induced-transfer defence. Until a verification flow for new or changed bank
    # details exists (known risk R2), anything short of allowlisted + verified + unchanged
    # is blocked outright.
    try:
        payee = store.get_payee(business_id, req.payee_id)
    except NotFoundError:
        return ["payee not found"]
    if not payee.allowlisted:
        reasons.append("payee is not on the allowlist")
    if not payee.verified:
        reasons.append("payee's bank details are not verified")
    if payee.details_changed_at is not None:
        reasons.append(
            f"payee's bank details were changed on {payee.details_changed_at.date().isoformat()}; "
            "payments are blocked until they are re-verified"
        )

    try:
        store.get_account(business_id, req.from_account_id)
    except NotFoundError:
        reasons.append("account not found")

    if req.pay_on < today:
        reasons.append(f"payment date {req.pay_on.isoformat()} is in the past")

    limits = get_limits(store, business_id)
    if req.amount > limits.per_payment:
        reasons.append(
            f"{sgd(req.amount)} is above the per-payment limit of {sgd(limits.per_payment)}"
        )
    same_day = sum(
        (
            p.amount
            for p in store.list_scheduled_payments(business_id, _COMMITTED, pay_on=req.pay_on)
            if p.id != exclude_payment_id
        ),
        Decimal("0"),
    )
    if same_day + req.amount > limits.per_day:
        reasons.append(
            f"payments dated {req.pay_on.isoformat()} would total {sgd(same_day + req.amount)}, "
            f"above the daily limit of {sgd(limits.per_day)}"
        )

    if req.bill_id is not None:
        try:
            bill = store.get_document(business_id, "bill", req.bill_id)
        except NotFoundError:
            reasons.append("bill not found")
        else:
            if bill.status is not DocumentStatus.OPEN:
                reasons.append(f"bill {bill.number} is {bill.status.value}")
            supplier = next(
                (c for c in store.list_counterparties(business_id) if c.id == bill.counterparty_id),
                None,
            )
            if supplier is not None and not _same_name(supplier.name, payee.name):
                reasons.append(f"bill {bill.number} is from a different supplier than this payee")
            pending = sum(
                (
                    p.amount
                    for p in store.list_scheduled_payments(
                        business_id, (PaymentStatus.SCHEDULED,), bill_id=bill.id
                    )
                    if p.id != exclude_payment_id
                ),
                Decimal("0"),
            )
            available = bill.amount - bill.amount_paid - pending
            if req.amount > available:
                reasons.append(
                    f"{sgd(req.amount)} is more than bill {bill.number}'s unpaid balance of "
                    f"{sgd(available)}"
                    + (f" ({sgd(pending)} is already scheduled)" if pending else "")
                )
    return reasons


def check_reminder(
    store: Store, sandbox: Sandbox, business_id: str, req: DraftReminderInput
) -> list[str]:
    try:
        invoice = store.get_document(business_id, "invoice", req.invoice_id)
    except NotFoundError:
        return ["invoice not found"]
    if invoice.status is not DocumentStatus.OPEN:
        return [f"invoice {invoice.number} is {invoice.status.value}, not open"]
    return []


def check_send_reminder(
    store: Store, sandbox: Sandbox, business_id: str, req: SendReminderInput
) -> list[str]:
    """A draft of this business, for an invoice still open, and not within a week of the last
    reminder for that invoice (no spamming the customer)."""
    try:
        reminder = store.get_reminder(business_id, req.reminder_id)
    except NotFoundError:
        return ["reminder draft not found"]
    if reminder.status != "draft":
        return [f"reminder {reminder.id} was already sent on {reminder.sent_on}"]
    reasons = check_reminder(
        store, sandbox, business_id, DraftReminderInput(invoice_id=reminder.invoice_id)
    )
    sent = [
        r.sent_on
        for r in store.list_reminders(business_id, reminder.invoice_id)
        if r.sent_on is not None
    ]
    if sent:
        last = max(sent)
        next_ok = last + timedelta(days=REMINDER_GAP_DAYS)
        if sandbox.today(business_id) < next_ok:
            reasons.append(
                f"a reminder for this invoice was sent on {last.isoformat()}; the next one can "
                f"go from {next_ok.isoformat()}"
            )
    return reasons


def check_mark_paid(
    store: Store, sandbox: Sandbox, business_id: str, req: MarkInvoicePaidInput
) -> list[str]:
    """The receipt must be real money in from this invoice's customer, not already tied to any
    invoice, and no more than the invoice's outstanding balance."""
    try:
        invoice = store.get_document(business_id, "invoice", req.invoice_id)
    except NotFoundError:
        return ["invoice not found"]
    try:
        txn = store.get_transaction(business_id, req.transaction_id)
    except NotFoundError:
        return ["bank transaction not found"]
    if invoice.status is not DocumentStatus.OPEN:
        return [f"invoice {invoice.number} is {invoice.status.value}, not open"]
    if txn.amount <= 0:
        return ["that transaction is money out, not a receipt"]
    reasons: list[str] = []
    if txn.counterparty_id != invoice.counterparty_id:
        reasons.append(f"the receipt is not from invoice {invoice.number}'s customer")
    linked = store.receipt_links(business_id).get(txn.id)
    if linked is not None:
        number = store.get_document(business_id, "invoice", linked).number
        reasons.append(f"the receipt is already recorded against invoice {number}")
    elif txn.id in match_settlements(store, business_id, "invoice").matched_transactions:
        reasons.append("the receipt already settles another, paid invoice")
    if txn.date < invoice.issue_date:
        reasons.append(f"the receipt is dated before invoice {invoice.number} was issued")
    outstanding = invoice.amount - invoice.amount_paid
    if txn.amount > outstanding:
        reasons.append(
            f"the receipt ({sgd(txn.amount)}) is more than invoice {invoice.number}'s "
            f"outstanding {sgd(outstanding)}"
        )
    return reasons


def check_floor(
    store: Store, sandbox: Sandbox, business_id: str, req: SetCashFloorInput
) -> list[str]:
    if req.floor < 0:
        return ["the floor can't be negative"]
    if req.floor > MAX_FLOOR:
        return [f"{sgd(req.floor)} is above the maximum floor of {sgd(MAX_FLOOR)}"]
    return []


def check_prefill(
    store: Store, sandbox: Sandbox, business_id: str, req: PrefillApplicationInput
) -> list[str]:
    """Only a product the business is eligible for, for a need that exists, can be pre-filled."""
    if load_catalogue().get(req.product_id) is None:
        return [f"unknown product {req.product_id}"]
    match, ranked = prefill_match(ToolContext(store, sandbox, business_id), req)
    if match.need.need is None:
        return [f"no financing need: {match.need.question or match.need.message}"]
    if ranked is None:
        elig = next(e for e in match.eligibility if e.product_id == req.product_id)
        return [f"not eligible for {elig.product_name}: " + "; ".join(elig.reasons)]
    return []


def check_submit(
    store: Store, sandbox: Sandbox, business_id: str, req: SubmitApplicationInput
) -> list[str]:
    """The draft must be this business's and still a draft, and the business must still be
    eligible now (facts can change between pre-fill and submission)."""
    try:
        app = store.get_application(business_id, req.application_id)
    except NotFoundError:
        return ["application not found"]
    if app.status is not ApplicationStatus.DRAFT:
        return [f"application {app.id} is already {app.status.value}"]
    product = load_catalogue().get(app.product_id)
    if product is None:
        return [f"product {app.product_id} is no longer offered"]
    elig = check(product, business_facts(store, sandbox, business_id).value)
    reasons = list(elig.reasons)
    q = quote(product, need_for(app))
    if q.amount > elig.max_amount:
        reasons.append(f"can lend at most {sgd(elig.max_amount)}; this needs {sgd(q.amount)}")
    return [f"no longer eligible: {r}" for r in reasons]


# --- Recorded adjustments and saved assumptions (chunk 13) ---------------------------------


def _month_label(key: str) -> str:
    return date(int(key[:4]), int(key[5:7]), 1).strftime("%b %Y")


def adjustment_problems(
    store: Store, sandbox: Sandbox, business_id: str, adj: Adjustment
) -> list[str]:
    """The rules every adjustment must meet, both when drafted and again when applied."""
    today = sandbox.today(business_id)
    months, why_not = open_months(store, business_id, today)
    if why_not is not None:
        return [f"adjustments need accrual books: {why_not}"]
    reasons: list[str] = []
    if adj.kind == "relabel":
        if adj.transaction_id is None:
            return ["a relabel needs the transaction_id of a bank payment"]
        try:
            txn = store.get_transaction(business_id, adj.transaction_id)
        except NotFoundError:
            return ["bank transaction not found"]
        if txn.amount >= 0:
            return [
                "that transaction is money in; only payments can be relabelled (receipts "
                "settle invoices and can't be moved out of receivables this way)"
            ]
        if txn.id in settled_bill_payments(store, business_id):
            reasons.append("that payment settles a supplier bill, so its cost is already counted")
        if txn.category not in RELABEL_FROM:
            reasons.append(f"a {txn.category.value} payment can't be relabelled")
        if adj.to_category is None or adj.to_category not in RELABEL_TO:
            reasons.append("choose the new category (an operating-cost line or owner_draw)")
        elif adj.to_category is txn.category:
            reasons.append(f"the payment is already counted as {txn.category.value}")
        if any(
            a.transaction_id == txn.id and a.id != adj.id
            for a in store.list_adjustments(business_id, "applied")
        ):
            reasons.append("that payment already has an applied relabel; undo it first")
    else:
        amount = adj.amount
        if amount is None:
            return [f"{adj.kind} needs an amount"]
        if adj.kind == "accrued_cost":
            if amount <= 0:
                reasons.append(
                    "an accrued cost must be a positive amount (a negative cost would raise "
                    "profit with no bill or receipt behind it)"
                )
            if adj.line not in ACCRUAL_LINES:
                reasons.append("choose the cost line (rent, utilities, software, ...)")
        else:  # stock_count
            if amount < 0:
                reasons.append("a stock count can't be negative")
            has_stock = bool(store.list_inventory_snapshots(business_id)) or any(
                b.line is BalanceLine.INVENTORY and b.amount != 0
                for b in store.list_opening_balances(business_id)
            )
            if not has_stock:
                reasons.append("this business has no stock records to correct")
            if any(
                a.kind == "stock_count" and a.month == adj.month and a.id != adj.id
                for a in store.list_adjustments(business_id, "applied")
            ):
                reasons.append(f"{adj.month} already has an applied stock count; undo it first")
        if amount > MAX_ADJUSTMENT:
            reasons.append(f"{sgd(amount)} is above the {sgd(MAX_ADJUSTMENT)} limit per adjustment")
    if adj.month not in months:
        span = f"{_month_label(months[0])} to {_month_label(months[-1])}"
        reasons.append(
            f"{adj.month} is closed: only the last {OPEN_MONTHS} complete months ({span}) can "
            "be adjusted"
        )
    return reasons


def check_draft_adjustment(
    store: Store, sandbox: Sandbox, business_id: str, req: DraftAdjustmentInput
) -> list[str]:
    if req.kind != "relabel" and req.month is None:
        return [f"{req.kind} needs the month (YYYY-MM)"]
    if len(store.list_adjustments(business_id, "draft")) >= MAX_DRAFTS:
        return [f"there are already {MAX_DRAFTS} drafts; apply or review them first"]
    try:
        adj = draft_from_args(ToolContext(store, sandbox, business_id), req, "new")
    except NotFoundError:
        return ["bank transaction not found"]
    return adjustment_problems(store, sandbox, business_id, adj)


def check_apply_adjustment(
    store: Store, sandbox: Sandbox, business_id: str, req: AdjustmentIdInput
) -> list[str]:
    try:
        adj = store.get_adjustment(business_id, req.adjustment_id)
    except NotFoundError:
        return ["adjustment not found"]
    if adj.status != "draft":
        return [f"adjustment {adj.id} is {adj.status}, not a draft"]
    if len(store.list_adjustments(business_id, "applied")) >= MAX_APPLIED:
        return [f"{MAX_APPLIED} adjustments are already applied (the limit)"]
    return adjustment_problems(store, sandbox, business_id, adj)


def check_undo_adjustment(
    store: Store, sandbox: Sandbox, business_id: str, req: AdjustmentIdInput
) -> list[str]:
    try:
        adj = store.get_adjustment(business_id, req.adjustment_id)
    except NotFoundError:
        return ["adjustment not found"]
    if adj.status != "applied":
        return [f"adjustment {adj.id} is {adj.status}, not applied"]
    months, why_not = open_months(store, business_id, sandbox.today(business_id))
    if why_not is not None or adj.month not in months:
        return [f"{adj.month} is closed, so its adjustments can't be undone"]
    return []


def check_save_assumption(
    store: Store, sandbox: Sandbox, business_id: str, req: SaveAssumptionInput
) -> list[str]:
    active = store.list_assumptions(business_id, "active")
    if len(active) >= MAX_ASSUMPTIONS:
        return [f"{MAX_ASSUMPTIONS} assumptions are already saved (the limit); remove one first"]
    if req.kind == "payment_delay":
        if req.customer_id is None or req.days is None:
            return ["a payment delay needs customer_id and days"]
        customer = next(
            (c for c in store.list_counterparties(business_id) if c.id == req.customer_id), None
        )
        if customer is None:
            return ["customer not found"]
        if customer.kind is CounterpartyKind.SUPPLIER:
            return ["that counterparty is a supplier, not a customer"]
        if any(a.counterparty_id == req.customer_id for a in active):
            return ["this customer already has a saved delay; remove it first"]
        return []
    if req.category is None or req.monthly_amount is None or req.start is None:
        return ["a recurring cost change needs category, monthly_amount and start"]
    reasons: list[str] = []
    today = sandbox.today(business_id)
    recurring = {r.category.value: r for r in detect_recurring(store, business_id, today)}
    item = recurring.get(req.category)
    if item is None or item.cadence != "monthly":
        reasons.append(f"there is no monthly recurring {req.category} cost in the forecast")
    if req.monthly_amount < 0:
        reasons.append("the monthly amount can't be negative")
    if req.monthly_amount > MAX_ASSUMED_COST:
        reasons.append(f"{sgd(req.monthly_amount)} is above the {sgd(MAX_ASSUMED_COST)} limit")
    if not today < req.start <= horizon_end(today):
        reasons.append(
            f"start must be after today and within the 13-week forecast (by "
            f"{horizon_end(today).isoformat()})"
        )
    if any(a.category is not None and a.category.value == req.category for a in active):
        reasons.append(f"{req.category} already has a saved change; remove it first")
    return reasons


def check_remove_assumption(
    store: Store, sandbox: Sandbox, business_id: str, req: AssumptionIdInput
) -> list[str]:
    try:
        a = store.get_assumption(business_id, req.assumption_id)
    except NotFoundError:
        return ["assumption not found"]
    if a.status != "active":
        return [f"assumption {a.id} is already {a.status}"]
    return []


GUARDS: dict[str, Guard] = {
    "draft_adjustment": check_draft_adjustment,
    "apply_adjustment": check_apply_adjustment,
    "undo_adjustment": check_undo_adjustment,
    "save_assumption": check_save_assumption,
    "remove_assumption": check_remove_assumption,
    "schedule_payment": check_payment,
    "draft_reminder": check_reminder,
    "send_reminder": check_send_reminder,
    "mark_invoice_paid": check_mark_paid,
    "set_cash_floor": check_floor,
    "prefill_application": check_prefill,
    "submit_application": check_submit,
}
