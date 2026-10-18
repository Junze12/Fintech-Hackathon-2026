"""Tool registry + gateway: what each role sees and can call, argument checks, audit."""

from decimal import Decimal
from pathlib import Path

import pytest

from copilot.policy.gateway import Gateway
from copilot.policy.guards import GUARDS
from copilot.policy.roles import CAPABILITY_TOOLS, TIERS, Actor, Role
from copilot.tools import default_registry
from copilot.tools.registry import Tool, ToolInput, ToolRegistry

ROOT = Path(__file__).resolve().parents[2]
BIZ = "biz-kopi"
READS = {
    "get_metrics",
    "get_ageing",
    "get_cash_trend",
    "get_health_ratios",
    "get_financial_statements",
    "get_financial_model",
    "get_break_even_and_value",
    "compare_periods",
    "get_expense_breakdown",
    "get_cash_position",
    "forecast_balance",
    "get_alerts",
    "get_obligations",
    "get_cash_summary",
    "run_what_if",
    "recommend_actions",
    "stress_test_cash",
    "compare_options",
    "get_reconciliation_exceptions",
    "find_financing",
    "list_applications",
    "list_payees",
    "list_bills",
    "list_invoices",
    "list_receipts",
    "list_reminders",
    "list_adjustments",
}
PAY = dict(payee_id="p-beans", from_account_id="a-ops", amount="100.00", pay_on="2026-09-30")


def actor(role, business_id=BIZ):
    return Actor(user_id=f"u-{role.label}", role=role, business_id=business_id, session_id="s")


@pytest.fixture
def gw(store, sandbox):
    return Gateway(store, sandbox)


# --- Registry ---------------------------------------------------------------


def test_tool_names_are_verb_noun_with_descriptions_and_strict_inputs():
    for tool in default_registry().all():
        assert "_" in tool.name and tool.name == tool.name.lower()
        assert len(tool.description) > 40
        assert tool.input_model.model_config["extra"] == "forbid"
        schema = tool.spec()["input_schema"]
        assert schema.get("additionalProperties") is False


def test_tools_shown_per_role(gw):
    names = {r: {s["name"] for s in gw.specs(actor(r))} for r in Role}
    assert names[Role.VIEWER] == READS
    staff = READS | {"draft_reminder", "set_cash_floor", "prefill_application", "draft_adjustment"}
    assert names[Role.STAFF] == staff
    owner_only = {
        "schedule_payment",
        "submit_application",
        "send_reminder",
        "mark_invoice_paid",
        "apply_adjustment",
        "undo_adjustment",
        "save_assumption",
        "remove_assumption",
    }
    assert names[Role.OWNER] == staff | owner_only


def test_registry_rejects_unsafe_definitions():
    class Loose(ToolInput):
        model_config = {"extra": "allow"}

    registry = ToolRegistry()
    loose = Tool("do_thing", "x", Loose, Role.VIEWER, "read", run=lambda c, a: None)
    with pytest.raises(ValueError, match="forbid"):
        registry.register(loose)
    with pytest.raises(ValueError, match="describe"):
        registry.register(Tool("pay_x", "x", ToolInput, Role.OWNER, "write", run=lambda c, a: 1))


# --- Gateway: roles and arguments --------------------------------------------


@pytest.mark.parametrize("role", [Role.VIEWER, Role.STAFF])
def test_lower_roles_cannot_pay_even_if_they_call_it(gw, store, role):
    result = gw.call(actor(role), "schedule_payment", PAY)
    assert result.outcome == "denied" and not result.ok
    assert result.pending is None
    assert store.list_scheduled_payments(BIZ) == []


def test_viewer_cannot_draft_but_staff_can(gw):
    args = {"invoice_id": "i-0098"}
    assert gw.call(actor(Role.VIEWER), "draft_reminder", args).outcome == "denied"
    result = gw.call(actor(Role.STAFF), "draft_reminder", args)
    assert result.outcome == "saved" and result.pending is None
    assert "Sunrise Events" in result.data.body
    assert "S$1,850.00" in result.data.body and "22 days overdue" in result.data.body


@pytest.mark.parametrize(
    "extra", [{"role": "owner"}, {"business_id": "biz-other"}, {"confirmed": True}]
)
def test_smuggled_arguments_are_rejected(gw, store, extra):
    result = gw.call(actor(Role.OWNER), "schedule_payment", {**PAY, **extra})
    assert result.outcome == "invalid"
    assert "Extra inputs are not permitted" in result.message
    assert store.list_scheduled_payments(BIZ) == []


@pytest.mark.parametrize(
    ("args", "fragment"),
    [
        ({**PAY, "amount": 100.5}, "float"),
        ({**PAY, "amount": "100.001"}, "2 decimal places"),
        ({**PAY, "amount": "-5"}, "greater than 0"),
        ({**PAY, "pay_on": "soon"}, "pay_on"),
        ("pay everyone", "arguments"),
    ],
)
def test_bad_arguments_are_invalid(gw, args, fragment):
    result = gw.call(actor(Role.OWNER), "schedule_payment", args)
    assert result.outcome == "invalid"
    assert fragment in result.message


def test_unknown_tool(gw):
    result = gw.call(actor(Role.OWNER), "transfer_all_funds", {})
    assert result.outcome == "invalid" and "unknown tool" in result.message


def test_blocked_write_reports_reasons(gw):
    result = gw.call(actor(Role.OWNER), "schedule_payment", {**PAY, "amount": "80000.00"})
    assert result.outcome == "blocked" and not result.ok
    assert "per-payment limit" in result.message


def test_not_found_is_an_error_not_a_crash(gw):
    result = gw.call(actor(Role.VIEWER), "list_bills", {"status": "open"})
    assert result.ok
    result = gw.call(actor(Role.STAFF), "draft_reminder", {"invoice_id": "nope"})
    assert result.outcome == "blocked" and "invoice not found" in result.message


# --- Results the LLM sees -----------------------------------------------------


def test_pending_result_hides_the_code_from_the_llm(gw):
    result = gw.call(actor(Role.OWNER), "schedule_payment", PAY)
    assert result.outcome == "pending"
    seen = str(result.for_llm())
    assert result.pending.code not in seen.replace(result.pending.id, "")
    assert "confirm" not in seen.lower().replace("confirmation code", "")


def test_read_tools_return_domain_numbers(gw):
    result = gw.call(actor(Role.VIEWER), "get_cash_position", {})
    data = result.for_llm()["data"]
    assert data["value"]["total"] == "25358.15"  # 13,358.15 + 12,000.00
    payees = gw.call(actor(Role.VIEWER), "list_payees", {}).for_llm()["data"]
    assert {p["account"] for p in payees} == {"••••1111", "••••2222"}


def test_cash_crunch_position_matches_ground_truth(load_scenario):
    sc = load_scenario("cash_crunch")
    gw = Gateway(sc.store, sc.sandbox)
    viewer = actor(Role.VIEWER, sc.business_id)
    value = gw.call(viewer, "get_cash_position", {}).data.value
    expected = sum(Decimal(v) for v in sc.truth["closing_balances"].values())
    assert value.total == expected
    alerts = gw.call(viewer, "get_alerts", {}).data
    assert alerts["alerts"].value[0].kind == "threshold"
    assert alerts["alerts"].value[0].severity == "critical"


# --- Audit ------------------------------------------------------------------


def test_every_call_is_audited_with_role_and_outcome(gw):
    gw.call(actor(Role.VIEWER), "get_cash_position", {})
    gw.call(actor(Role.STAFF), "schedule_payment", PAY)
    gw.call(actor(Role.OWNER), "schedule_payment", {**PAY, "role": "owner"})
    entries = gw.audit.entries(BIZ)
    assert [(e.role, e.tool, e.outcome) for e in entries] == [
        (Role.VIEWER, "get_cash_position", "ok"),
        (Role.STAFF, "schedule_payment", "denied"),
        (Role.OWNER, "schedule_payment", "invalid"),
    ]
    assert entries[1].reason == "needs the owner role; you are staff"
    assert entries[2].params["role"] == "owner"  # the attempt itself is kept as evidence


def test_audit_masks_account_numbers(gw):
    gw.call(actor(Role.OWNER), "schedule_payment", {**PAY, "reference": "send to 001-234567-8 now"})
    gw.call(actor(Role.OWNER), "schedule_payment", {**PAY, "account_number": "001-234567-8"})
    params = [e.params for e in gw.audit.entries(BIZ)]
    assert params[0]["reference"] == "send to ••••5678 now"
    assert params[0]["amount"] == "100.00"  # money is not mistaken for an account number
    assert params[0]["pay_on"] == "2026-09-30"  # nor is a date (regression, 4d)
    assert params[1]["account_number"] == "••••5678"


# --- set_cash_floor (staff, personal) ------------------------------------------------


def test_floor_is_staff_only_personal_and_audited(gw):
    viewer, staff = actor(Role.VIEWER), actor(Role.STAFF)
    assert gw.call(viewer, "set_cash_floor", {"floor": "5000.00"}).outcome == "denied"
    result = gw.call(staff, "set_cash_floor", {"floor": "5000.00"})
    assert result.outcome == "saved" and result.pending is None  # no confirmation needed
    assert gw.call(staff, "get_alerts", {}).data["floor_source"] == "your saved floor"
    other = Actor(user_id="u-other", role=Role.STAFF, business_id=BIZ, session_id="s2")
    assert gw.call(other, "get_alerts", {}).data["floor_source"] == "default"
    once = gw.call(staff, "get_alerts", {"floor": "1.00"}).data
    assert (once["floor"], once["floor_source"]) == (Decimal("1.00"), "this request")
    blocked = gw.call(staff, "set_cash_floor", {"floor": "20000000.00"})
    assert blocked.outcome == "blocked"
    outcomes = [e.outcome for e in gw.audit.entries(BIZ) if e.tool == "set_cash_floor"]
    assert outcomes == ["denied", "saved", "blocked"]


def test_what_if_through_the_gateway_with_json_args(load_scenario):
    sc = load_scenario("cash_crunch")
    gw = Gateway(sc.store, sc.sandbox)
    viewer = actor(Role.VIEWER, sc.business_id)
    changes = [{"kind": "add_one_off", "amount": "-1000.00", "date": "2026-10-10", "label": "x"}]
    result = gw.call(viewer, "run_what_if", {"changes": changes})
    assert result.ok and result.data.value.low_point_change == Decimal("-1000.00")
    # Unknown ids come back as an error, extra fields are rejected, nothing is written.
    bad = gw.call(
        viewer,
        "run_what_if",
        {"changes": [{"kind": "delay_payment", "bill_id": "nope", "days": 3}]},
    )
    assert not bad.ok and "not found" in bad.message
    sneaky = gw.call(viewer, "recommend_actions", {"buffer": "0", "business_id": "biz-other"})
    assert not sneaky.ok and sneaky.outcome == "invalid"
    rec = gw.call(viewer, "recommend_actions", {})
    assert rec.ok and rec.data.value.funding_need.amount == Decimal("13025.81")


# --- Registry hardening (4d) -------------------------------------------------------


def test_tools_with_external_effects_must_be_confirmed():
    def noop(c, a):
        return None

    registry = ToolRegistry()
    unconfirmed = Tool(
        "pay_x", "x", ToolInput, Role.OWNER, "write", run=noop, describe=noop, external_effect=True
    )
    with pytest.raises(ValueError, match="external effect must be confirmed"):
        registry.register(unconfirmed)
    external = {t.name for t in default_registry().all() if t.external_effect}
    assert external == {
        "schedule_payment",
        "submit_application",
        "send_reminder",
        "mark_invoice_paid",
        "apply_adjustment",
        "undo_adjustment",
        "save_assumption",
        "remove_assumption",
    }
    assert all(default_registry().get(n).needs_confirmation for n in external)
    assert all(default_registry().get(n).min_role is Role.OWNER for n in external)


def test_every_write_tool_has_exactly_one_guard():
    writes = {t.name for t in default_registry().all() if t.kind == "write"}
    assert set(GUARDS) == writes


def test_tiers_capabilities_and_docs_agree_with_the_registry():
    registry = default_registry()
    for role, capabilities in TIERS.items():
        if role is Role.VIEWER:
            continue
        for capability in capabilities:
            for name in CAPABILITY_TOOLS[capability]:
                assert registry.get(name).min_role is role, (capability, name)
    by_role = {r: {t.name for t in registry.all() if t.min_role is r} for r in Role}
    assert by_role[Role.VIEWER] == {t.name for t in registry.all() if t.kind == "read"}

    doc = (ROOT / "docs" / "security" / "self-assessment.md").read_text(encoding="utf-8")
    rows = {
        cells[0]: {n.strip() for n in cells[2].split(",")}
        for line in doc.splitlines()
        if line.startswith("| ")
        and (cells := [c.strip() for c in line.strip("|").split("|")])
        and cells[0] in {"Viewer", "Staff", "Owner"}
    }
    assert {Role[k.upper()]: v for k, v in rows.items()} == by_role


def test_no_tool_argument_is_offered_as_a_number_and_then_refused_as_a_float():
    """Regression (Claude evidence 2026-10-18, T-IX-03): money was described to the model as
    "number or string" but refused as a float, so it retried 50000.0 until the step limit."""
    import json

    from pydantic import TypeAdapter, ValidationError

    from copilot.schemas import MONEY_JSON, Money

    assert TypeAdapter(Money).json_schema() == MONEY_JSON  # covers nested arguments too
    for tool in default_registry().all():
        model = tool.input_model
        for name, prop in model.model_json_schema().get("properties", {}).items():
            if '"number"' not in json.dumps(prop):
                continue
            try:
                model.model_validate({name: 12.5})
            except ValidationError as exc:
                refused = [e for e in exc.errors() if e["loc"][:1] == (name,)]
                floats = [e for e in refused if "must not be a float" in e["msg"]]
                assert not floats, (tool.name, name)
