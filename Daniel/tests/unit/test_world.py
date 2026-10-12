"""The scripted world (sandbox/world.py): replaying it hands-off must reproduce the forward
answer key in ground_truth.json, because both come from the same events."""

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from copilot.ingest import ingest_folder
from copilot.sandbox.bank import Sandbox
from copilot.sandbox.world import FILENAME, WorldScript
from copilot.schemas import DocumentStatus, PaymentStatus, ScheduledPayment, TransactionCategory
from copilot.store import Store

SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"
CRUNCH = SYNTHETIC_DIR / "cash_crunch"
B2B = SYNTHETIC_DIR / "concentrated_b2b"


def fresh(folder):
    truth = json.loads((folder / "ground_truth.json").read_text(encoding="utf-8"))
    store = Store(":memory:")
    ingest_folder(store, folder)
    sandbox = Sandbox(store)
    as_of = date.fromisoformat(truth["as_of"])
    sandbox.set_today(truth["business_id"], as_of)
    return store, sandbox, truth["business_id"], as_of, truth


def replay(sandbox, world, biz, start, until):
    outcomes, day = [], start
    while day < until:
        day += timedelta(days=1)
        sandbox.set_today(biz, day)
        outcomes += world.replay_day(sandbox, biz, day)
    return outcomes


def total(sandbox, biz, day):
    return sum(sandbox.balances(biz, day).values(), Decimal("0"))


def test_script_loads_without_rejects():
    for folder in (CRUNCH, B2B):
        world = WorldScript.load(folder)
        assert world.rejected == [] and world.warnings == []
        assert world.end == date(2026, 12, 27)  # last day of the 13-week horizon
        assert world.events == sorted(world.events, key=lambda e: e.date)


def test_bad_rows_are_rejected_with_reasons(tmp_path):
    text = (CRUNCH / FILENAME).read_text(encoding="utf-8").splitlines()
    text.append("ev-9999,2026-10-02,wire_out,,,a-ops,-1.00,,,,,bad kind")
    text.append("ev-9998,not-a-date,debit,,,a-ops,-1.00,rent,,,,bad date")
    (tmp_path / FILENAME).write_text("\n".join(text) + "\n", encoding="utf-8")
    world = WorldScript.load(tmp_path)
    assert [r.line for r in world.rejected] == [len(text) - 1, len(text)]
    assert "kind" in world.rejected[0].reason and "date" in world.rejected[1].reason


def test_missing_script_is_empty_with_warning(tmp_path):
    world = WorldScript.load(tmp_path)
    assert world.events == [] and world.end is None
    assert "only runs scheduled payments" in world.warnings[0]


def test_cash_crunch_replay_matches_answer_key_then_the_big_bill_bounces():
    store, sandbox, biz, as_of, truth = fresh(CRUNCH)
    world = WorldScript.load(CRUNCH)
    weeks = truth["forward"]["weeks"]
    outcomes = replay(sandbox, world, biz, as_of, date.fromisoformat(weeks[4]["end"]))
    for week in weeks[:5]:  # weeks 1-5, before the S$85,000 bill: exact to the cent
        assert total(sandbox, biz, date.fromisoformat(week["end"])) == Decimal(week["end_balance"])
    assert all(o.outcome == "executed" for o in outcomes)

    outcomes = replay(sandbox, world, biz, sandbox.today(biz), date(2026, 11, 5))
    bounced = [o for o in outcomes if o.outcome == "blocked"]
    assert len(bounced) == 1
    assert bounced[0].date == date(2026, 11, 5) and bounced[0].reason == "insufficient funds"
    assert "MFI-88120" in bounced[0].description and bounced[0].amount == Decimal("-85000.00")
    bill = store.get_document(biz, "bill", "b-bulk-stock")
    assert bill.status is DocumentStatus.OPEN  # unpaid: now overdue
    # Everything else still happened, so the balance is the answer key plus the unpaid bill.
    day = date.fromisoformat(weeks[5]["end"])
    replay(sandbox, world, biz, sandbox.today(biz), day)
    assert total(sandbox, biz, day) == Decimal(weeks[5]["end_balance"]) + Decimal("85000.00")


def test_b2b_replay_matches_all_13_weeks():
    _, sandbox, biz, as_of, truth = fresh(B2B)
    world = WorldScript.load(B2B)
    replay(sandbox, world, biz, as_of, world.end)
    for week in truth["forward"]["weeks"]:
        assert total(sandbox, biz, date.fromisoformat(week["end"])) == Decimal(week["end_balance"])


def test_world_transactions_are_categorised_and_new_documents_appear():
    store, sandbox, biz, as_of, _ = fresh(CRUNCH)
    replay(sandbox, WorldScript.load(CRUNCH), biz, as_of, date(2026, 10, 6))
    new = [t for t in store.list_transactions(biz) if t.id.startswith("sbx-world-")]
    by_desc = {t.description: t.category for t in new}
    assert by_desc["RENT OCT 26 UNIT 05-12"] is TransactionCategory.RENT
    assert by_desc["GIRO CR Kallang Corner Stores INV-1065"] is TransactionCategory.SALES
    assert store.get_document(biz, "invoice", "i-0065").status is DocumentStatus.PAID
    assert store.get_document(biz, "invoice", "i-0066").number == "INV-1066"  # issued 10-05


def test_replay_needs_the_clock_on_that_day():
    _, sandbox, biz, as_of, _ = fresh(CRUNCH)
    with pytest.raises(ValueError):
        WorldScript.load(CRUNCH).replay_day(sandbox, biz, as_of + timedelta(days=1))


def test_bill_the_owner_is_paying_through_the_copilot_is_skipped():
    store, sandbox, biz, as_of, _ = fresh(CRUNCH)
    store.add_scheduled_payment(
        ScheduledPayment(
            id="sp-own",
            business_id=biz,
            payee_id="p-meridian",
            from_account_id="a-ops",
            amount=Decimal("61898.43"),
            pay_on=date(2026, 10, 10),
            status=PaymentStatus.SCHEDULED,
            bill_id="b-0048",
            created_at="2026-09-30T09:00:00+08:00",
        )
    )
    outcomes = replay(sandbox, WorldScript.load(CRUNCH), biz, as_of, date(2026, 10, 3))
    skip = next(o for o in outcomes if "BL-5048" in o.description)
    assert skip.outcome == "skipped" and "through the copilot" in skip.reason
    assert store.get_document(biz, "bill", "b-0048").status is DocumentStatus.OPEN
    events = [e for e in sandbox.events(biz) if e.object_id == "b-0048"]
    assert events[-1].outcome == "skipped"  # logged, not silently dropped


def test_reserve_transfer_moves_money_between_own_accounts():
    _, sandbox, biz, as_of, _ = fresh(B2B)
    before = sandbox.balances(biz, as_of)
    replay(sandbox, WorldScript.load(B2B), biz, as_of, date(2026, 10, 25))
    events = [e for e in sandbox.events(biz) if e.action == "world_transfer"]
    assert len(events) == 1 and events[0].amount == Decimal("5000.00")
    after = sandbox.balances(biz, date(2026, 10, 25))
    assert after["a-res"] - before["a-res"] == Decimal("5000.00")
