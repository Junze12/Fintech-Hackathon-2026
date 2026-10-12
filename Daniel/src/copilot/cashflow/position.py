"""Current cash position across accounts. Account numbers are never included."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    CopilotModel,
    DataCoverage,
    DomainResult,
    Driver,
    Id,
    Money,
    UntrustedText,
)
from copilot.store import Store


class AccountBalance(CopilotModel):
    account_id: Id
    name: UntrustedText  # from the import file (known risk R7)
    balance: Money


class CashPosition(CopilotModel):
    as_of: date
    accounts: list[AccountBalance]
    total: Money


def cash_position(
    store: Store, sandbox: Sandbox, business_id: str, as_of: date | None = None
) -> DomainResult[CashPosition]:
    as_of = as_of or sandbox.today(business_id)
    accounts = store.list_accounts(business_id)
    balances = sandbox.balances(business_id, as_of)
    rows = [AccountBalance(account_id=a.id, name=a.name, balance=balances[a.id]) for a in accounts]
    total = sum((r.balance for r in rows), Decimal("0"))
    txns = store.list_transactions(business_id, end=as_of)
    return DomainResult[CashPosition](
        value=CashPosition(as_of=as_of, accounts=rows, total=total),
        drivers=[Driver(label=r.name, amount=r.balance) for r in rows],
        data_coverage=DataCoverage(
            period_start=min((a.opening_date for a in accounts), default=as_of),
            period_end=as_of,
            record_count=len(txns),
        ),
        warnings=[] if accounts else ["No accounts found"],
    )
