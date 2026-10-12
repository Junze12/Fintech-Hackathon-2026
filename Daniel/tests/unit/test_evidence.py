"""Evidence export (deliverable #6): complete, masked, and the audit chain head is published.

Offline only: the mock runs the task cases and the fooled model the red-team cases.
"""

from __future__ import annotations

import csv
import json
import re

import pytest

from copilot.agent.mock_rules import RuleBasedLLM
from copilot.evals import redteam, tasks
from copilot.evals.evidence import STORYLINE, _case_evidence, _Redactor, export
from copilot.schemas import mask

TASK_CASES = ["T-CF-08", "T-FI-03"]  # a confirmed payment, a confirmed submission
RT_CASES = ["RT-IT-01", "RT-IT-08", "RT-DE-01", "RT-DE-02"]  # injection, code, account, canary


def _full_numbers() -> list[str]:
    numbers = []
    for name in ("accounts.csv", "payees.csv"):
        for path in redteam.SCENARIOS_DIR.glob(f"*/{name}"):
            with path.open(encoding="utf-8") as f:
                numbers += [row["account_number"] for row in csv.DictReader(f)]
    return numbers


def _all_text(folder) -> dict[str, str]:
    return {str(p): p.read_text(encoding="utf-8") for p in folder.rglob("*") if p.is_file()}


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("evidence")
    runs = {
        "mock": export("mock", out, case_ids=TASK_CASES),
        "fooled": export("fooled", out, case_ids=RT_CASES),
    }
    return out, runs


def test_one_file_per_case_and_index_lists_them(exported):
    out, runs = exported
    for mode, ids, suite in (("mock", TASK_CASES, "tasks"), ("fooled", RT_CASES, "redteam")):
        folder = out / f"{mode}-partial"  # a case filter never touches the full run's folder
        assert not (out / mode).exists()
        index = (folder / "index.md").read_text(encoding="utf-8")
        data = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        assert sorted(c["id"] for c in data["cases"]) == sorted(ids)
        for case_id in ids:
            assert (folder / suite / f"{case_id}.md").exists()
            assert f"[{case_id}]({suite}/{case_id}.md)" in index
        assert runs[mode].passed


def test_nothing_secret_is_written(exported):
    out, _ = exported
    numbers = _full_numbers()
    assert numbers  # the scan is only meaningful if it has something to look for
    for path, text in _all_text(out).items():
        digits = re.sub(r"\D", "", text)
        for number in numbers:
            assert number not in text, f"{path}: full account number"
            assert re.sub(r"\D", "", number) not in digits, f"{path}: account digits"
        assert not re.search(r"confirm\s*#?\s*\d{4}\b", text, re.IGNORECASE), path
        assert "cnry-" not in text, f"{path}: canary"


def test_confirmed_payment_shows_the_whole_trail(exported):
    out, _ = exported
    text = (out / "mock-partial" / "tasks" / "T-CF-08.md").read_text(encoding="utf-8")
    write_rows = [line for line in text.splitlines() if "`schedule_payment` | write" in line]
    outcomes = [re.search(r"\*\*(\w+)\*\*", row).group(1) for row in write_rows]  # type: ignore[union-attr]
    assert outcomes == ["pending", "confirmed", "executed"]
    assert "| execute_payment |" in text  # the sandbox bank moved the money
    assert "-S$61,898.43" in text  # and the balance table shows it
    assert "confirm ****" in text  # the user's code, masked


def test_blocked_injected_transfer_is_recorded_with_reason(exported):
    out, _ = exported
    text = (out / "fooled-partial" / "redteam" / "RT-IT-01.md").read_text(encoding="utf-8")
    assert "**blocked** | payee is not on the allowlist" in text
    assert "None: the sandbox bank was not asked" in text
    assert "★ Demo video storyline, step 4 of 4." in text


@pytest.mark.parametrize("case_id", ["RT-IT-02", "RT-DE-04"])  # RT-DE-04 loads two businesses
def test_chain_heads_match_the_audit_log(case_id):
    case = next(c for c in redteam.load_cases() if c.id == case_id)
    run = redteam.run_case_session(case, None)
    ev = _case_evidence("redteam", case, run)
    audit = run.session.gateway.audit
    businesses = [r[0] for r in run.session.gateway.store.conn.execute("SELECT id FROM businesses")]
    assert {c.business_id for c in ev.chains} == set(businesses)
    for chain in ev.chains:
        assert chain.ok and chain.head == audit.head(chain.business_id)
    # every write attempt in the audit log is in the evidence
    writes = [e.seq for e in audit.entries(run.session.actor.business_id) if e.kind == "write"]
    assert writes == [r.seq for r in ev.audit if r.kind == "write"]
    assert writes or case_id == "RT-DE-04"  # a read-only attack: nothing to write


def test_redactor_masks_codes_canary_and_numbers():
    case = next(c for c in tasks.load_cases() if c.id == "T-CF-08")
    run = tasks.run_case_session(case, RuleBasedLLM())
    r = _Redactor(run.session)
    number = redteam.secret_numbers(run.session)[0]
    raw = f"Reply 'confirm 4821' or CONFIRM 1234. {run.session.canary} paid to {number}."
    out = r.text(raw)
    assert out == f"Reply 'confirm ****' or CONFIRM ****. [canary] paid to {mask(number)}."
    assert r.text("INV-1062 on 2026-10-09: S$1,234.00") == "INV-1062 on 2026-10-09: S$1,234.00"


def test_skipped_mock_case_is_listed_with_its_reason(tmp_path):
    run = export("mock", tmp_path, case_ids=["T-IX-01"])
    text = (tmp_path / "mock-partial" / "tasks" / "T-IX-01.md").read_text(encoding="utf-8")
    assert run.cases[0].skipped and "**Result: SKIP**" in text and "skipped on the mock" in text


def test_full_offline_export(tmp_path):
    fooled = export("fooled", tmp_path)
    mock = export("mock", tmp_path)
    assert len(fooled.cases) == len(redteam.load_cases())
    assert len(mock.cases) == len(tasks.load_cases())
    assert fooled.passed and mock.passed
    assert all(ch.ok for c in fooled.cases + mock.cases for ch in c.chains)
    ids = {c.id for c in fooled.cases + mock.cases}
    assert set(STORYLINE) <= ids
    assert (tmp_path / "fooled" / "index.md").exists() and (tmp_path / "mock" / "index.md").exists()


def test_a_leaked_code_is_reported_without_its_value():
    # The failure message ends up in the published scorecard, so it must not carry the code.
    leaks = redteam._leaks("your code is 4821", {"numbers": [], "names": []}, ["4821"])
    assert leaks == ["a confirmation code"]
