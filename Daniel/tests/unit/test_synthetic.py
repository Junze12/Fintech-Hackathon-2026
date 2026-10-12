"""Tests for the synthetic data generator (src/copilot/synthetic.py)."""

import filecmp
import json
from decimal import Decimal
from pathlib import Path

import pytest

from copilot.adapters.csv_folder import CsvFolderAdapter
from copilot.sandbox.bank import Sandbox
from copilot.store import Store
from copilot.synthetic import AS_OF, SCENARIOS, generate

COMMITTED = Path(__file__).resolve().parents[2] / "data" / "synthetic"


@pytest.fixture(scope="module", params=sorted(SCENARIOS))
def generated(request, tmp_path_factory):
    folder = tmp_path_factory.mktemp(request.param)
    business = generate(SCENARIOS[request.param], seed=42)
    business.write(folder)
    return request.param, folder, business.ground_truth


def test_same_seed_is_byte_identical(tmp_path):
    for key, scenario in SCENARIOS.items():
        generate(scenario, seed=42).write(tmp_path / "a" / key)
        generate(scenario, seed=42).write(tmp_path / "b" / key)
        comparison = filecmp.dircmp(tmp_path / "a" / key, tmp_path / "b" / key)
        assert not comparison.diff_files and not comparison.left_only


def test_different_seed_differs(tmp_path):
    scenario = SCENARIOS["cash_crunch"]
    generate(scenario, seed=1).write(tmp_path / "a")
    generate(scenario, seed=2).write(tmp_path / "b")
    assert (tmp_path / "a" / "transactions.csv").read_text() != (
        tmp_path / "b" / "transactions.csv"
    ).read_text()


def test_committed_data_matches_generator(tmp_path):
    """data/synthetic must be regenerated whenever the generator changes."""
    for key, scenario in SCENARIOS.items():
        generate(scenario, seed=42).write(tmp_path / key)
        comparison = filecmp.dircmp(tmp_path / key, COMMITTED / key)
        assert not comparison.diff_files, (
            f"{key} is stale; run python scripts/generate_synthetic.py"
        )


def test_loads_through_adapter_with_no_rejects(generated):
    _, folder, truth = generated
    result = CsvFolderAdapter().load(folder)
    assert result.rejected == []
    assert result.warnings == []
    assert len(result.transactions) == len(truth["true_category"])


def test_ground_truth_balances_match_the_store(generated):
    _, folder, truth = generated
    store = Store(":memory:")
    store.save_import(CsvFolderAdapter().load(folder))
    balances = Sandbox(store).balances(truth["business_id"], as_of=AS_OF)
    assert {k: str(v) for k, v in balances.items()} == truth["closing_balances"]


def test_history_never_overdraws(generated):
    _, _, truth = generated
    assert Decimal(truth["history_min_operating_balance"]) > 0


def test_monthly_group_totals_add_up(generated):
    """Category totals and group totals are two views of the same money."""
    _, _, truth = generated
    for month in truth["monthly_totals"].values():
        by_cat = sum(Decimal(v) for v in month["by_category"].values())
        by_group = sum(Decimal(v) for v in month["by_group"].values())
        assert by_cat == by_group


def test_forward_truth_shape(generated):
    _, _, truth = generated
    forward = truth["forward"]
    assert len(forward["weeks"]) == 13
    assert forward["weeks"][0]["start"] == "2026-09-28"  # Monday of the week containing Oct 1
    assert Decimal(forward["tolerance"]) > 0


def test_cash_crunch_story():
    truth = generate(SCENARIOS["cash_crunch"], seed=42).ground_truth
    low = truth["forward"]["low_point"]
    assert Decimal(low["balance"]) < 0
    assert 4 <= low["week"] <= 6
    assert "b-bulk-stock" in truth["open_bills"]


def test_concentrated_b2b_story():
    truth = generate(SCENARIOS["concentrated_b2b"], seed=42).ground_truth
    assert truth["largest_customer"]["id"] == "c-tidewater"
    assert (
        Decimal("0.55")
        <= Decimal(truth["largest_customer"]["share_of_invoiced"])
        <= Decimal("0.65")
    )
    assert truth["overdue_invoices"]
    assert Decimal(truth["forward"]["low_point"]["balance"]) > 0  # healthy cash, different story


def test_committed_ground_truth_is_valid_json():
    for key in SCENARIOS:
        data = json.loads((COMMITTED / key / "ground_truth.json").read_text(encoding="utf-8"))
        assert data["scenario"] == key
