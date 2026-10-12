"""Assign a TransactionCategory to every uncategorised transaction.

Deterministic rules, no LLM (CLAUDE.md: domain modules never call the LLM). First match wins:
  1. already categorised in the source data -> keep
  2. the counterparty has a default_category -> use it
  3. keyword rule on the description, which must also match the money direction
  4. counterparty kind + direction: customer paying in -> sales, paying a supplier -> cogs
  5. otherwise stay uncategorised (never guessed)

Descriptions are untrusted external text. They are only matched against fixed regexes here,
so instructions hidden in them have no effect.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from copilot.schemas import (
    CopilotModel,
    Counterparty,
    CounterpartyKind,
    DataCoverage,
    DomainResult,
    Driver,
    Transaction,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

Direction = Literal["in", "out", "any"]


@dataclass(frozen=True)
class KeywordRule:
    name: str
    pattern: re.Pattern[str]
    category: Cat
    direction: Direction


def _rule(name: str, regex: str, category: Cat, direction: Direction) -> KeywordRule:
    return KeywordRule(name, re.compile(regex, re.IGNORECASE), category, direction)


KEYWORD_RULES: tuple[KeywordRule, ...] = (
    _rule("payroll", r"\b(salary|salaries|payroll|cpf)\b", Cat.PAYROLL, "out"),
    _rule("rent", r"\b(rent|rental)\b", Cat.RENT, "out"),
    _rule(
        "utilities",
        r"\b(sp services|sp group|utilities|electricity|water bill)\b",
        Cat.UTILITIES,
        "out",
    ),
    _rule("tax", r"\b(iras|gst|income tax|corporate tax)\b", Cat.TAX, "out"),
    _rule(
        "own-account transfer",
        r"\btransfer (to|from) (own|reserve|operating|savings)\b",
        Cat.TRANSFER,
        "any",
    ),
    _rule(
        "loan repayment",
        r"\bloan (repayment|instalment|installment)\b",
        Cat.LOAN_REPAYMENT,
        "out",
    ),
    _rule("loan drawdown", r"\bloan (disbursement|drawdown)\b", Cat.FINANCING_INFLOW, "in"),
    _rule("marketing", r"\b(advertising|ads|marketing)\b", Cat.MARKETING, "out"),
    _rule("software", r"\b(subscription|saas|software licen[cs]e)\b", Cat.SOFTWARE, "out"),
    _rule("bank charges", r"\b(service charge|bank charge|bank fee)\b", Cat.OTHER, "out"),
    _rule(
        "card settlement",
        r"\b(card settlement|nets settlement|merchant settlement)\b",
        Cat.SALES,
        "in",
    ),
    _rule("interest income", r"\binterest credit\b", Cat.OTHER_INCOME, "in"),
)


def _direction_ok(direction: Direction, txn: Transaction) -> bool:
    if direction == "any":
        return True
    return (txn.amount > 0) == (direction == "in")


def classify(txn: Transaction, counterparty: Counterparty | None) -> tuple[Cat, str]:
    """Return (category, name of the rule that decided it)."""
    if txn.category is not Cat.UNCATEGORISED:
        return txn.category, "already categorised"
    if counterparty is not None and counterparty.default_category is not None:
        return counterparty.default_category, "counterparty default"
    for rule in KEYWORD_RULES:
        if _direction_ok(rule.direction, txn) and rule.pattern.search(txn.description):
            return rule.category, f"keyword: {rule.name}"
    if counterparty is not None:
        if txn.amount > 0 and counterparty.kind in (
            CounterpartyKind.CUSTOMER,
            CounterpartyKind.BOTH,
        ):
            return Cat.SALES, "customer receipt"
        if txn.amount < 0 and counterparty.kind in (
            CounterpartyKind.SUPPLIER,
            CounterpartyKind.BOTH,
        ):
            return Cat.COGS, "supplier payment"
    return Cat.UNCATEGORISED, "no rule matched"


class CategorisationSummary(CopilotModel):
    total: int
    changed: int
    uncategorised: int
    by_category: dict[str, int]


def categorise(store: Store, business_id: str) -> DomainResult[CategorisationSummary]:
    """Categorise every transaction of one business and save the result."""
    transactions = store.list_transactions(business_id)
    counterparties = {c.id: c for c in store.list_counterparties(business_id)}

    changes: dict[str, Cat] = {}
    final: Counter[str] = Counter()
    rules_fired: Counter[str] = Counter()
    for txn in transactions:
        category, rule = classify(txn, counterparties.get(txn.counterparty_id or ""))
        final[category.value] += 1
        rules_fired[rule] += 1
        if category is not txn.category:
            changes[txn.id] = category
    store.update_categories(business_id, changes)

    total = len(transactions)
    uncategorised = final[Cat.UNCATEGORISED.value]
    warnings = []
    if uncategorised:
        share = uncategorised / total
        warnings.append(
            f"{uncategorised} transactions ({share:.0%}) remain uncategorised; "
            "margins and expense breakdowns exclude them"
        )

    if transactions:
        coverage = DataCoverage(
            period_start=transactions[0].date,
            period_end=transactions[-1].date,
            record_count=total,
        )
    else:
        business = store.get_business(business_id)
        coverage = DataCoverage(
            period_start=business.incorporated_on,
            period_end=business.incorporated_on,
            record_count=0,
        )
        warnings.append("no transactions to categorise")

    return DomainResult[CategorisationSummary](
        value=CategorisationSummary(
            total=total,
            changed=len(changes),
            uncategorised=uncategorised,
            by_category=dict(sorted(final.items())),
        ),
        drivers=[
            Driver(label=rule, detail=f"{count} transactions")
            for rule, count in rules_fired.most_common()
        ],
        data_coverage=coverage,
        warnings=warnings,
    )
