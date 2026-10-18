from datetime import date
from decimal import Decimal

import pytest

from copilot.reconcile import estimate_payment_delays
from copilot.schemas import Counterparty, CounterpartyKind


@pytest.mark.parametrize("scenario", ["cash_crunch", "concentrated_b2b"])
def test_delays_match_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    result = estimate_payment_delays(s.store, s.business_id)
    for cid, facts in s.truth["customers"].items():
        estimated = result.value[cid]
        assert abs(estimated.mean_delay_days - Decimal(str(facts["observed_mean_delay_days"]))) <= (
            Decimal("0.5")
        ), cid
        assert estimated.unmatched == 0
    assert result.warnings == []


def test_slow_payer_is_identified(load_scenario):
    s = load_scenario("concentrated_b2b")
    delays = estimate_payment_delays(s.store, s.business_id).value
    slowest = max(delays.values(), key=lambda d: d.mean_delay_days)
    assert slowest.customer_id == "c-lumen" and slowest.mean_delay_days > 30


def test_customer_without_history_defaults_to_zero(store):
    store.add_counterparty(
        Counterparty(
            id="c-new", business_id="biz-kopi", name="New Co", kind=CounterpartyKind.CUSTOMER
        )
    )
    result = estimate_payment_delays(store, "biz-kopi")
    assert result.value["c-new"].mean_delay_days == 0
    assert any("c-new" in w for w in result.warnings)
    assert result.data_coverage.period_start <= date(2026, 9, 14)
