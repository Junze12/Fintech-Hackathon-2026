"""Chunk 9 API: demo sessions, dashboard panels, chat with confirmation, clock, limits.

Runs offline on the rule-based assistant (conftest blanks the API key). The API adds no
capability: these tests check that role and business come only from the session, that writes
still need the user's own confirmation, and that panels match ground truth.
"""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="needs the api extra")

from fastapi.testclient import TestClient  # noqa: E402

from copilot.agent.mock_rules import RuleBasedLLM  # noqa: E402
from copilot.api.app import create_app  # noqa: E402
from copilot.api.sessions import SessionStore  # noqa: E402
from copilot.runtime import open_scenario  # noqa: E402
from copilot.schemas import Role  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRUTH = json.loads((ROOT / "data/synthetic/cash_crunch/ground_truth.json").read_text("utf-8"))
CODE = re.compile(r"confirm (\d{4})")


def mock_opener(folder: Path, role: Role, assistant: str):
    """Treats every assistant as the free mock, so cap tests never need a key or network."""
    return open_scenario(folder, role, llm=RuleBasedLLM())


def client(store: SessionStore | None = None) -> TestClient:
    return TestClient(
        create_app(store if store is not None else SessionStore(), opener=mock_opener)
    )


def signed_in(role: str = "owner", scenario: str = "cash_crunch", **kw) -> TestClient:
    c = client(**kw)
    r = c.post("/api/session", json={"scenario": scenario, "role": role})
    assert r.status_code == 200, r.text
    return c


def total_cash(c: TestClient) -> Decimal:
    return Decimal(c.get("/api/dashboard").json()["panels"]["cash"]["data"]["value"]["total"])


# --- Sessions -------------------------------------------------------------------------------


def test_everything_but_options_needs_a_session():
    c = client()
    assert c.get("/api/options").status_code == 200
    assert c.get("/api/session").status_code == 401
    assert c.get("/api/dashboard").status_code == 401
    assert c.post("/api/chat", json={"message": "hi"}).status_code == 401
    assert c.post("/api/clock/advance", json={"days": 1}).status_code == 401


def test_sign_in_sets_a_strict_http_only_cookie_and_sign_out_ends_it():
    c = client()
    r = c.post("/api/session", json={"scenario": "cash_crunch", "role": "viewer"})
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
    assert r.json()["role"] == "viewer" and r.json()["today"] == TRUTH["as_of"]
    assert r.headers["cache-control"] == "no-store"
    assert c.delete("/api/session").status_code == 200
    assert c.get("/api/session").status_code == 401


def test_options_offer_no_paid_model_without_a_key(monkeypatch):
    assert client().get("/api/options").json()["assistants"] == ["mock"]
    r = client().post(
        "/api/session", json={"scenario": "cash_crunch", "role": "owner", "assistant": "claude"}
    )
    assert r.status_code == 422


def test_roles_can_be_restricted_for_a_hosted_demo(monkeypatch):
    monkeypatch.setenv("COPILOT_API_ROLES", "staff,viewer")
    c = client()
    assert c.get("/api/options").json()["roles"] == ["staff", "viewer"]
    r = c.post("/api/session", json={"scenario": "cash_crunch", "role": "owner"})
    assert r.status_code == 422


def test_unknown_scenario_or_role_is_rejected():
    c = client()
    assert c.post("/api/session", json={"scenario": "x", "role": "owner"}).status_code == 422
    assert c.post(
        "/api/session", json={"scenario": "cash_crunch", "role": "admin"}
    ).status_code == (422)


def test_role_and_business_cannot_be_smuggled_into_a_request():
    c = signed_in("viewer")
    for body in ({"message": "hi", "role": "owner"}, {"message": "hi", "business_id": "x"}):
        assert c.post("/api/chat", json=body).status_code == 422
    assert c.post("/api/clock/advance", json={"days": 1, "role": "owner"}).status_code == 422
    assert c.get("/api/session").json()["role"] == "viewer"


def test_each_cookie_sees_only_its_own_session():
    store = SessionStore()
    a = signed_in("owner", "cash_crunch", store=store)
    b = signed_in("viewer", "concentrated_b2b", store=store)
    assert a.get("/api/session").json()["business_name"].startswith("Straits Harbour")
    assert b.get("/api/session").json()["business_name"].startswith("Clearpath")
    assert len(store) == 2


def test_oldest_session_is_evicted_at_the_limit():
    store = SessionStore(max_sessions=2)
    first = signed_in(store=store)
    signed_in(store=store)
    signed_in(store=store)
    assert len(store) == 2 and first.get("/api/session").status_code == 401


def test_idle_sessions_expire():
    now = [0.0]
    store = SessionStore(idle_seconds=60, clock=lambda: now[0])
    c = signed_in(store=store)
    now[0] = 59
    assert c.get("/api/session").status_code == 200
    now[0] = 59 + 61
    assert c.get("/api/session").status_code == 401


def test_paid_assistant_has_a_message_cap(monkeypatch):
    monkeypatch.setattr("copilot.api.app.has_api_key", lambda: True)
    c = client(SessionStore(max_messages=2))
    body = {"scenario": "cash_crunch", "role": "viewer", "assistant": "claude"}
    assert c.post("/api/session", json=body).json()["messages_left"] == 2
    for _ in range(2):
        assert c.post("/api/chat", json={"message": "how much cash?"}).status_code == 200
    assert c.post("/api/chat", json={"message": "how much cash?"}).status_code == 429


# --- Dashboard --------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["viewer", "staff", "owner"])
def test_dashboard_panels_match_ground_truth_for_every_role(role):
    d = signed_in(role).get("/api/dashboard").json()
    panels = d["panels"]
    assert all(p["ok"] for p in panels.values()), {k: p["message"] for k, p in panels.items()}
    cash = panels["cash"]["data"]["value"]
    assert cash["total"] == str(sum(Decimal(v) for v in TRUTH["closing_balances"].values()))
    receivables = panels["ageing"]["data"]["receivables"]["value"]
    assert receivables["total"] == str(
        sum(Decimal(v) for v in TRUTH["receivables_ageing"].values())
    )
    assert panels["health"]["data"]["debt_service_cover"]["value"]["dscr"] == "0.61"
    assert panels["alerts"]["data"]["alerts"]["value"]  # cash_crunch has alerts
    assert d["metrics_period"] == {"start": "2026-06-01", "end": "2026-08-31"}
    assert d["today"] == TRUTH["as_of"] and d["pending"] is None


def test_money_is_never_a_float():
    d = signed_in().get("/api/dashboard").json()

    def floats(x):
        if isinstance(x, float):
            yield x
        elif isinstance(x, dict):
            for v in x.values():
                yield from floats(v)
        elif isinstance(x, list):
            for v in x:
                yield from floats(v)

    assert list(floats(d)) == []


def test_imported_names_come_back_as_plain_data():
    """The poisoned scenario's instruction-like names are returned as text and do nothing."""
    c = signed_in("owner", "prompt_injection")
    before = total_cash(c)
    d = c.get("/api/dashboard").json()
    text = json.dumps(d)
    assert "<untrusted" not in text  # wrapping is for the LLM only; the frontend shows text
    assert total_cash(c) == before and d["pending"] is None


# --- Chat and clock ---------------------------------------------------------------------------


def test_owner_payment_runs_only_after_the_users_own_confirmation():
    c = signed_in("owner")
    before = total_cash(c)
    r = c.post("/api/chat", json={"message": "Pay bill BL-5048"}).json()
    assert r["pending"] and "S$61,898.43" in r["pending"]
    assert total_cash(c) == before  # nothing moves while pending
    assert c.get("/api/dashboard").json()["pending"] == r["pending"]
    code = CODE.search(r["pending"]).group(1)
    done = c.post("/api/chat", json={"message": f"confirm {code}"}).json()
    assert any("Paid S$61,898.43" in n for n in done["notices"])
    assert total_cash(c) == before - Decimal("61898.43")


def test_wrong_code_cancels_the_payment():
    c = signed_in("owner")
    before = total_cash(c)
    r = c.post("/api/chat", json={"message": "Pay bill BL-5048"}).json()
    wrong = "0000" if CODE.search(r["pending"]).group(1) != "0000" else "1111"
    c.post("/api/chat", json={"message": f"confirm {wrong}"})
    assert total_cash(c) == before and c.get("/api/dashboard").json()["pending"] is None


def test_viewer_cannot_pay_through_the_api():
    c = signed_in("viewer")
    r = c.post("/api/chat", json={"message": "Pay bill BL-5048"}).json()
    assert r["pending"] is None
    assert "schedule_payment" not in [t["tool"] for t in r["trace"] if t["outcome"] == "pending"]


def test_message_length_is_limited():
    c = signed_in()
    assert c.post("/api/chat", json={"message": "x" * 2001}).status_code == 422
    assert c.post("/api/chat", json={"message": ""}).status_code == 422


def test_clock_advance_reports_the_week():
    c = signed_in("viewer")
    rep = c.post("/api/clock/advance", json={"days": 7}).json()
    assert rep["ok"] and rep["start"] == "2026-09-30" and rep["end"] == "2026-10-07"
    assert rep["world"]  # customers paid, bills went out
    assert c.get("/api/session").json()["today"] == "2026-10-07"
    assert c.post("/api/clock/advance", json={"days": 8}).status_code == 422


# --- Statements (chunk 12) ------------------------------------------------------------------


def test_statements_endpoint_matches_the_accrual_key():
    c = signed_in("viewer")
    d = c.get("/api/statements", params={"period": "last_12_months"}).json()
    assert d["ok"], d["message"]
    s = d["data"]["value"]
    assert s["basis"] == "accrual" and s["pnl"]["net_profit"] == "-22467.49"
    sep = TRUTH["accrual"]["months"]["2026-09"]["balance_sheet"]
    assert s["balance_sheet"]["total_assets"] == sep["total_assets"]
    assert s["checks"]["balanced"] and s["checks"]["cash_matches_bank"]
    one = c.get("/api/statements", params={"statement": "pnl", "month": "2026-08"}).json()
    assert one["data"]["value"]["balance_sheet"] is None
    assert c.get("/api/statements", params={"month": "2026-13"}).status_code == 422
    assert c.get("/api/statements", params={"period": "decade"}).status_code == 422


def test_model_endpoint_gives_three_balanced_cases():
    c = signed_in("viewer")
    d = c.get("/api/model").json()
    assert d["ok"], d["message"]
    v = d["data"]["value"]
    assert set(v["cases"]) == {"worst", "expected", "best"}
    assert v["first_month"] == "2026-10" and v["starts_from"] == "2026-09-30"
    assert all(case["checks"]["balanced"] for case in v["cases"].values())
    assert isinstance(v["cases"]["expected"]["outlook"]["lowest_cash"], str)  # money as text
    one = c.get("/api/model", params={"case": "best", "view": "monthly", "year": 3}).json()
    rows = one["data"]["value"]["cases"]["best"]["monthly"]
    assert [r["month"] for r in rows][0] == "2028-10" and len(rows) == 12
    assert not c.get("/api/model", params={"view": "monthly"}).json()["ok"]  # one case only
    assert c.get("/api/model", params={"year": 4}).status_code == 422
    assert c.get("/api/model", params={"sales_growth_pct": "50"}).json()["ok"]  # ignored


def test_stress_endpoint_gives_daily_bands_curve_and_bridge():
    c = signed_in("viewer")
    d = c.get("/api/stress").json()
    assert d["ok"], d["message"]
    v = d["data"]["value"]
    assert v["failures"]["most_likely_day"] == "2026-11-05"
    row = v["daily"][0]
    assert set(row) == {"date", "forecast", "p10", "p50", "p90"} and isinstance(row["p50"], str)
    assert len(v["curve"]) == 21 and set(v["curve"][0]) == {"shock", "survival_pct"}
    assert [s["key"] for s in v["bridge"]["steps"]][0] == "cash"
    shocked = c.get(
        "/api/stress", params={"shock_amount": "20000", "shock_date": "2026-10-15"}
    ).json()
    assert shocked["ok"] and shocked["data"]["value"]["shock"]["amount"] == "20000"
    assert not c.get("/api/stress", params={"shock_amount": "5000"}).json()["ok"]  # no date
    assert c.get("/api/stress", params={"shock_amount": "-5"}).status_code == 422
    assert c.get("/api/stress", params={"target_pct": 50}).status_code == 422


def test_plans_endpoint_gives_table_frontier_and_daily_rows():
    c = signed_in("viewer")
    d = c.get("/api/plans").json()
    assert d["ok"], d["message"]
    v = d["data"]["value"]
    table = v["table"]
    assert table[0]["key"] == "nothing" and sum(r["recommended"] for r in table) == 1
    assert set(table[0]) >= {"name", "survival_pct", "cost_vs_nothing", "gap_on_risk_day"}
    assert all(set(p) == {"key", "cost", "survival_pct"} for p in v["frontier"])
    assert v["cost_bridge"][-1]["key"] == "total" and isinstance(v["best"]["cost_vs_nothing"], str)
    assert set(v["line_daily"][0]) == {"date", "drawn_p10", "drawn_p50", "drawn_p90"}
    assert len(v["best_daily"]) == 88
    assert c.get("/api/plans", params={"chase_on_time_pct": 101}).status_code == 422
    assert c.get("/api/plans", params={"customer_loss_pct": 20}).json()["ok"]


# --- Adjustments (chunk 13) ------------------------------------------------------------------


def test_adjustments_endpoint_and_both_statement_views():
    c = signed_in("owner")
    d = c.get("/api/adjustments").json()
    assert d["ok"] and d["data"]["open_months"] == ["2026-07", "2026-08", "2026-09"]
    assert d["data"]["adjustments"] == [] and d["data"]["saved_assumptions"] == []
    msg = "Record an accrued cost of S$2,000 for professional fees in September 2026 and apply it."
    pending = c.post("/api/chat", json={"message": msg}).json()["pending"]
    code = re.search(r"confirm (\d{4})", pending).group(1)
    c.post("/api/chat", json={"message": f"confirm {code}"})
    d = c.get("/api/adjustments").json()
    assert [a["status"] for a in d["data"]["adjustments"]] == ["applied"]
    adjusted = c.get("/api/statements", params={"statement": "pnl"}).json()["data"]["value"]
    assert adjusted["pnl"]["net_profit"] == "-6105.30"
    assert adjusted["adjustments"]["net_profit_as_imported"] == "-4105.30"
    imported = c.get("/api/statements", params={"view": "as_imported"}).json()["data"]["value"]
    assert imported["pnl"]["net_profit"] == "-4105.30"
    assert c.get("/api/statements", params={"view": "whatever"}).status_code == 422
    assert c.post("/api/adjustments", json={}).status_code == 405  # read-only


def test_reconciliation_endpoint_lists_exceptions_read_only():
    c = signed_in("viewer", scenario="messy_books")
    d = c.get("/api/reconciliation").json()
    assert d["ok"], d["message"]
    v = d["data"]["value"]
    assert v["counts"] == {"high": 5, "medium": 4, "low": 11}
    first = v["exceptions"][0]
    assert first["severity"] == "high" and first["amount"] == "12453.58"
    assert set(first) >= {"kind", "reason", "next_step", "documents", "transactions"}
    high = c.get("/api/reconciliation", params={"min_severity": "high"}).json()["data"]["value"]
    assert {x["severity"] for x in high["exceptions"]} == {"high"}
    assert c.get("/api/reconciliation", params={"min_severity": "all"}).status_code == 422
    assert c.post("/api/reconciliation", json={}).status_code == 405
    clean = signed_in("viewer").get("/api/reconciliation").json()["data"]["value"]
    assert clean["counts"]["high"] == 0


# --- Speed: skipping the headline's plan search, and the per-session cache (2026-10-16) -------


def test_stress_without_best_plan_changes_only_the_headline(monkeypatch):
    from copilot.cashflow import stress

    c = signed_in()
    full = c.get("/api/stress").json()["data"]["value"]
    calls = []
    real = stress._best_plan
    monkeypatch.setattr(stress, "_best_plan", lambda *a, **k: calls.append(1) or real(*a, **k))
    fast = c.get("/api/stress", params={"best_plan": "false"}).json()["data"]["value"]
    assert calls == []  # the 56-plan search was skipped
    assert {k for k in full if full[k] != fast[k]} == {"headline"}
    assert fast["survival_pct"] == full["survival_pct"] and fast["bridge"] == full["bridge"]


def test_reads_are_cached_per_session_and_cleared_by_chat_and_clock():
    c = signed_in()
    first = c.get("/api/stress", params={"best_plan": "false"}).json()
    assert c.get("/api/stress", params={"best_plan": "false"}).json() == first
    before = total_cash(c)
    reply = c.post("/api/chat", json={"message": "Pay bill BL-5048"}).json()
    code = CODE.search(reply["pending"]).group(1)
    c.post("/api/chat", json={"message": f"confirm {code}"})
    assert total_cash(c) == before - Decimal("61898.43")  # not a stale cached dashboard
    week = c.get("/api/dashboard").json()["today"]
    c.post("/api/clock/advance", json={"days": 7})
    assert c.get("/api/dashboard").json()["today"] != week


def test_cache_is_bounded_and_keyed_by_query():
    from copilot.api.sessions import MAX_CACHED

    c = signed_in()
    a = c.get("/api/statements", params={"period": "month"}).json()
    b = c.get("/api/statements", params={"period": "quarter"}).json()
    assert a["data"]["value"]["period"] != b["data"]["value"]["period"]
    for m in range(1, MAX_CACHED + 3):
        c.get("/api/statements", params={"month": f"2026-{(m % 9) + 1:02d}"})
    assert c.get("/api/statements", params={"period": "month"}).json() == a
