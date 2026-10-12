"""Moving the simulated clock forward, one day at a time (reached via Gateway.advance_clock).

For each day:
  1. set the sandbox clock to that day
  2. replay the scripted world for that day (customers pay, direct debits, supplier bills the
     business pays itself, new invoices and bills)
  3. run every payment the owner scheduled for that day. The payment guard runs again first
     (known risk R8): if the payee was un-verified or its bank details changed, or the limits
     are used up since the owner confirmed, the payment is blocked, not executed.
Then the alerts are re-evaluated and any new (or more severe) ones are reported.

This is a demo control used by the UI, not an LLM tool, so nothing in a chat message or an
imported document can move the clock. Every step is audited.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from copilot.cashflow.alerts import CashAlert, new_alerts
from copilot.policy.audit import AuditLog
from copilot.policy.guards import check_scheduled_execution
from copilot.policy.roles import Actor
from copilot.sandbox.bank import Sandbox
from copilot.sandbox.world import WorldOutcome, WorldScript
from copilot.schemas import CopilotModel, Id, Money, PaymentStatus, Role, UntrustedText, sgd
from copilot.store import Store
from copilot.tools.read_tools import ranked_alerts
from copilot.tools.registry import ToolContext

MAX_ADVANCE_DAYS = 28
SCHEDULER_USER = "system-scheduler"


class PaymentRun(CopilotModel):
    payment_id: Id
    date: date
    description: UntrustedText  # payee name and bill number
    amount: Money
    outcome: Literal["executed", "blocked", "rejected"]
    reason: str | None = None


class ClockReport(CopilotModel):
    ok: bool
    message: str
    start: date
    end: date
    world: list[WorldOutcome] = []
    payments: list[PaymentRun] = []
    new_alerts: list[CashAlert] = []
    warnings: list[str] = []


def advance(
    store: Store,
    sandbox: Sandbox,
    world: WorldScript,
    audit: AuditLog,
    actor: Actor,
    days: int,
) -> ClockReport:
    business_id = actor.business_id
    start = sandbox.today(business_id)
    problem = _check(days, start, world)
    if problem is not None:
        audit.log(actor, "advance_clock", "system", {"days": days}, "invalid", problem)
        return ClockReport(ok=False, message=problem, start=start, end=start)

    ctx = ToolContext(store=store, sandbox=sandbox, business_id=business_id, user_id=actor.user_id)
    before = ranked_alerts(ctx).value
    scheduler = Actor(
        user_id=SCHEDULER_USER,
        role=Role.OWNER,
        business_id=business_id,
        session_id=actor.session_id,
    )
    world_log: list[WorldOutcome] = []
    payments: list[PaymentRun] = []
    day = start
    for _ in range(days):
        day += timedelta(days=1)
        sandbox.set_today(business_id, day)
        world_log += world.replay_day(sandbox, business_id, day)
        payments += _run_due_payments(store, sandbox, audit, scheduler, day)

    after = ranked_alerts(ctx).value
    fresh = new_alerts(before, after)
    message = _summary(start, day, world_log, payments, fresh)
    audit.log(actor, "advance_clock", "system", {"days": days}, "executed", message)
    return ClockReport(
        ok=True,
        message=message,
        start=start,
        end=day,
        world=world_log,
        payments=payments,
        new_alerts=fresh,
        warnings=world.warnings,
    )


def _check(days: int, start: date, world: WorldScript) -> str | None:
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= MAX_ADVANCE_DAYS:
        return f"days must be a whole number from 1 to {MAX_ADVANCE_DAYS}"
    if world.end is not None and start + timedelta(days=days) > world.end:
        return (
            f"the simulated world ends on {world.end.isoformat()}; "
            f"today is {start.isoformat()}, so the clock can't move {days} days"
        )
    return None


def _run_due_payments(
    store: Store, sandbox: Sandbox, audit: AuditLog, scheduler: Actor, day: date
) -> list[PaymentRun]:
    business_id = scheduler.business_id
    payees = {p.id: p.name for p in store.list_payees(business_id)}
    runs = []
    for payment in store.list_scheduled_payments(business_id, (PaymentStatus.SCHEDULED,)):
        if payment.pay_on > day:
            continue
        params = payment.model_dump(mode="json", include={"id", "payee_id", "amount", "bill_id"})
        description = f"Payment to {payees.get(payment.payee_id, payment.payee_id)}"
        if payment.bill_id:
            bill = store.get_document(business_id, "bill", payment.bill_id)
            description += f" for bill {bill.number}"
        reasons = check_scheduled_execution(store, sandbox, business_id, payment)
        if reasons:
            reason = "; ".join(reasons)
            store.update_payment_status(business_id, payment.id, PaymentStatus.BLOCKED)
            audit.log(scheduler, "execute_scheduled_payment", "write", params, "blocked", reason)
            runs.append(_run(payment.id, day, description, payment.amount, "blocked", reason))
            continue
        result = sandbox.execute_payment(business_id, payment.id)
        if result.outcome == "executed":
            audit.log(scheduler, "execute_scheduled_payment", "write", params, "executed")
            runs.append(_run(payment.id, day, description, payment.amount, "executed", None))
        else:
            audit.log(
                scheduler, "execute_scheduled_payment", "write", params, "rejected", result.reason
            )
            runs.append(
                _run(payment.id, day, description, payment.amount, "rejected", result.reason)
            )
    return runs


def _run(payment_id, day, description, amount, outcome, reason) -> PaymentRun:
    return PaymentRun(
        payment_id=payment_id,
        date=day,
        description=description,
        amount=amount,
        outcome=outcome,
        reason=reason,
    )


def _summary(
    start: date,
    end: date,
    world: list[WorldOutcome],
    payments: list[PaymentRun],
    fresh: list[CashAlert],
) -> str:
    received = sum(
        (o.amount for o in world if o.kind == "receipt" and o.outcome == "executed"), Decimal("0")
    )
    paid = sum(
        (
            -o.amount
            for o in world
            if o.kind in ("debit", "bill_payment") and o.outcome == "executed"
        ),
        Decimal("0"),
    )
    bounced = [o for o in world if o.outcome == "blocked"]
    parts = [
        f"Clock moved from {start.isoformat()} to {end.isoformat()}.",
        f"Customers paid {sgd(received)}; {sgd(paid)} went out in bills and direct debits.",
    ]
    if bounced:
        parts.append(f"{len(bounced)} payment(s) bounced for lack of funds.")
    done = [p for p in payments if p.outcome == "executed"]
    stopped = [p for p in payments if p.outcome != "executed"]
    if done:
        parts.append(f"{len(done)} scheduled payment(s) made.")
    if stopped:
        parts.append(f"{len(stopped)} scheduled payment(s) stopped.")
    parts.append(f"{len(fresh)} new alert(s)." if fresh else "No new alerts.")
    return " ".join(parts)
