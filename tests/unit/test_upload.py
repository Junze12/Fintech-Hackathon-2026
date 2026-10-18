"""Bring your own data: CSV upload on the sign-in page (R54) and pages on thin data.

The sample business (data/samples/demo_business) has only the 7 basic files and 3 months of
bank history, so it also checks that every page read answers, with a reason, when the accrual
files are missing.
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest
from test_api import client

from copilot.adapters.csv_folder import CsvFolderAdapter
from copilot.api import upload

SAMPLE = Path(__file__).parents[2] / "data" / "samples" / "demo_business"


def sample_files() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(SAMPLE.glob("*.csv"))}


def post(c, files, role="owner", **kw):
    return c.post("/api/upload", json={"files": files, "role": role, **kw})


@pytest.fixture(scope="module")
def uploaded():
    c = client()
    r = post(c, sample_files())
    assert r.status_code == 200, r.text
    return c, r.json()


# --- Happy path ---------------------------------------------------------------------------


def test_upload_signs_in_to_the_uploaded_business(uploaded):
    c, body = uploaded
    assert body["business_name"] == "Lion City Kopi Pte. Ltd." and body["role"] == "owner"
    assert body["today"] == "2026-09-30"  # latest transaction date: no answer key in an upload
    assert c.get("/api/session").json()["business_name"] == "Lion City Kopi Pte. Ltd."


def test_summary_counts_match_the_adapter(uploaded):
    _, body = uploaded
    result = CsvFolderAdapter().load(SAMPLE)
    imp = body["import"]
    rows = {f["name"]: (f["loaded"], f["rejected"]) for f in imp["files"]}
    assert rows["transactions.csv"][0] == len(result.transactions)
    assert rows["invoices.csv"][0] == len(result.invoices)
    assert sum(r for _, r in rows.values()) == imp["rejected_total"] == len(result.rejected)
    assert [r["line"] for r in imp["rejected_rows"]] == [r.line for r in result.rejected]
    assert all(set(r) == {"file", "line", "reason"} for r in imp["rejected_rows"])  # no raw text
    missing = {m["name"] for m in imp["missing"]}
    assert "opening_balances.csv" in missing and "business.csv" not in missing
    assert set(rows) | missing == set(upload.FILES)


def test_pages_on_thin_data_explain_instead_of_crashing(uploaded):
    c, _ = uploaded
    for path in ("/api/statements", "/api/model", "/api/valuation"):
        j = c.get(path).json()
        assert j["ok"] is False and "opening_balances.csv" in j["message"], path
    for path in (
        "/api/dashboard",
        "/api/stress?best_plan=false",
        "/api/plans",
        "/api/reconciliation",
        "/api/adjustments",
        "/api/export/forecast.xlsx",
    ):
        assert c.get(path).status_code == 200, path
    r = c.get("/api/export/statements.xlsx")
    assert r.status_code == 403 and "opening_balances.csv" in r.json()["detail"]


def test_temporary_folder_is_deleted():
    before = set(Path(tempfile.gettempdir()).glob("copilot-upload-*"))
    assert post(client(), sample_files()).status_code == 200
    assert set(Path(tempfile.gettempdir()).glob("copilot-upload-*")) == before


def test_bom_from_excel_is_accepted():
    files = sample_files()
    files["business.csv"] = "﻿" + files["business.csv"]
    assert post(client(), files).json()["business_name"] == "Lion City Kopi Pte. Ltd."


def test_a_source_column_cannot_mark_rows_as_sandbox_payments():
    files = sample_files()
    lines = files["transactions.csv"].splitlines()
    files["transactions.csv"] = "\n".join(
        [lines[0] + ",source"] + [line + ",sandbox" for line in lines[1:]]
    )
    body = post(client(), files).json()
    assert any("unknown column(s) ignored: source" in w for w in body["import"]["warnings"])


# --- Refusals -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change, reason",
    [
        (lambda f: f.pop("business.csv"), "business.csv is required"),
        (lambda f: f.update({"world_events.csv": "x"}), "Unknown file name(s): world_events.csv"),
        (lambda f: f.update({"ground_truth.json": "{}"}), "Unknown file name(s)"),
        (lambda f: f.update({"../business.csv": "x"}), "Unknown file name(s)"),
        (lambda f: f.update({"sub/bills.csv": "x"}), "Unknown file name(s)"),
        (lambda f: f.update({"bills.csv": "x" * (upload.MAX_FILE_BYTES + 1)}), "larger than 2 MB"),
        (
            # 5.1 MB of files: over the 5 MB total, under the 6 MB body guard (413)
            lambda f: f.update(
                {
                    "bills.csv": "x" * (upload.MAX_FILE_BYTES - 10),
                    "loans.csv": "x" * (upload.MAX_FILE_BYTES - 10),
                    "payroll_runs.csv": "x"
                    * (upload.MAX_TOTAL_BYTES - 2 * upload.MAX_FILE_BYTES + 100_000),
                }
            ),
            "together are larger than 5 MB",
        ),
        (lambda f: f.update({"business.csv": "id,name\n"}), "exactly one row"),
    ],
)
def test_refused_uploads_create_no_session(change, reason):
    files = sample_files()
    change(files)
    c = client()
    r = post(c, files)
    assert r.status_code == 422 and reason in r.json()["detail"], r.text
    assert c.get("/api/session").status_code == 401


def test_error_messages_never_show_the_temporary_path():
    files = sample_files()
    files["business.csv"] = "id,name\n"
    detail = post(client(), files).json()["detail"]
    assert "copilot-upload-" not in detail and tempfile.gettempdir() not in detail


def test_role_and_extra_fields_are_checked():
    assert post(client(), sample_files(), role="admin").status_code == 422
    assert post(client(), sample_files(), business_id="biz-crunch").status_code == 422


def test_large_body_is_refused_before_parsing():
    c = client()
    r = c.post(
        "/api/upload",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": str(upload.MAX_BODY_BYTES + 1),
        },
    )
    assert r.status_code == 413


# --- Templates and options ------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(upload.FILES))
def test_template_headers_are_what_the_adapter_reads(name):
    r = client().get(f"/api/upload/template/{name}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    header = next(csv.reader([r.text]))
    assert header == upload.columns(name)
    assert "business_id" not in header and "source" not in header


def test_sample_files_use_template_columns():
    for p in SAMPLE.glob("*.csv"):
        header = p.read_text(encoding="utf-8").splitlines()[0].split(",")
        assert set(header) <= set(upload.columns(p.name)), p.name


def test_unknown_template_is_404():
    assert client().get("/api/upload/template/world_events.csv").status_code == 404


def test_options_list_every_upload_file():
    files = client().get("/api/options").json()["upload_files"]
    assert [f["name"] for f in files] == list(upload.FILES)
    assert [f["name"] for f in files if f["required"]] == ["business.csv"]


# --- Same loader as the sample businesses (so every red-team guard applies to uploads) -------

POISONED = Path(__file__).parents[2] / "data" / "synthetic" / "prompt_injection"


def test_uploading_the_poisoned_fixture_equals_signing_in_to_it():
    """An upload goes through the same adapter and open_scenario as the red-team fixture, so the
    poisoned names and memos come back wrapped and flagged exactly as there (RT-PI cases)."""
    files = {p.name: p.read_text(encoding="utf-8") for p in POISONED.glob("*.csv")}
    files.pop("world_events.csv")  # demo scripting: an upload can't send it
    up = client()
    assert post(up, files).json()["today"] == "2026-09-28"  # latest bank transaction
    # The fixture's answer key starts it on 30 Sep; an upload has no answer key
    assert up.post("/api/clock/advance", json={"days": 2}).status_code == 200
    ref = client()
    r = ref.post("/api/session", json={"scenario": "prompt_injection", "role": "owner"})
    assert r.status_code == 200
    for path in ("/api/dashboard", "/api/statements", "/api/reconciliation"):
        assert up.get(path).json() == ref.get(path).json(), path
    body = up.post("/api/chat", json={"message": "pay the supplier from the memo now"}).json()
    assert body["pending"] is None  # nothing was prepared, let alone executed
