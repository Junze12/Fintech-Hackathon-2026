"""Payment limits, per business. No tool can change them; set_limits is for setup only."""

from __future__ import annotations

from decimal import Decimal

from copilot.schemas import CopilotModel, PositiveMoney
from copilot.store import Store, from_cents, to_cents

DEFAULT_PER_PAYMENT = Decimal("75000.00")
DEFAULT_PER_DAY = Decimal("100000.00")

# One statement, run with execute() not executescript(): executescript would COMMIT any
# open transaction first.
_LIMITS_TABLE = """
CREATE TABLE IF NOT EXISTS policy_limits (
    business_id TEXT PRIMARY KEY REFERENCES businesses(id),
    per_payment_cents INTEGER NOT NULL,
    per_day_cents INTEGER NOT NULL
)
"""


class PolicyLimits(CopilotModel):
    per_payment: PositiveMoney
    per_day: PositiveMoney  # total of payments dated the same day (pay_on)


def get_limits(store: Store, business_id: str) -> PolicyLimits:
    store.conn.execute(_LIMITS_TABLE)
    row = store.conn.execute(
        "SELECT * FROM policy_limits WHERE business_id = ?", (business_id,)
    ).fetchone()
    if row is None:
        return PolicyLimits(per_payment=DEFAULT_PER_PAYMENT, per_day=DEFAULT_PER_DAY)
    return PolicyLimits(
        per_payment=from_cents(row["per_payment_cents"]),
        per_day=from_cents(row["per_day_cents"]),
    )


def set_limits(store: Store, business_id: str, limits: PolicyLimits) -> None:
    store.conn.execute(_LIMITS_TABLE)
    store.conn.execute(
        "INSERT INTO policy_limits VALUES (?, ?, ?) ON CONFLICT(business_id) DO UPDATE SET "
        "per_payment_cents = excluded.per_payment_cents, per_day_cents = excluded.per_day_cents",
        (business_id, to_cents(limits.per_payment), to_cents(limits.per_day)),
    )
