"""Streamlit smoke test: the app loads, a demo conversation works, and roles change behaviour.
Skipped when Streamlit isn't installed (it is an optional extra: pip install -e ".[ui]")."""

import re
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[2] / "src" / "copilot" / "ui" / "app.py")


def run(at, message):
    at.chat_input[0].set_value(message).run()
    return at


def shown(elements):
    r"""Text as the user sees it: the UI escapes $ as \$ so Markdown doesn't treat it as maths."""
    return [e.value.replace(r"\$", "$") for e in elements]


def test_owner_pays_bill_and_balance_panel_updates():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert at.metric[0].value == "S$156,526.85"
    assert "Mock LLM (rules, no AI)" in " ".join(c.value for c in at.caption)

    run(at, "pay bill BL-5048")
    pending = [w for w in shown(at.warning) if "confirm" in w]
    assert pending and pending[-1].startswith("Pay S$61,898.43 to Meridian")
    code = re.search(r"confirm (\d{4})", pending[-1]).group(1)

    run(at, f"confirm {code}")
    assert not at.exception
    assert any("Paid S$61,898.43" in i for i in shown(at.info))
    assert at.metric[0].value == "S$94,628.42"


def test_viewer_cannot_pay():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.selectbox[1].set_value("Viewer").run()
    run(at, "pay bill BL-5048")
    assert not at.exception
    assert any("Only the business owner" in m for m in shown(at.markdown))
    assert at.metric[0].value == "S$156,526.85"


UNESCAPED_DOLLAR = re.compile(r"(?<!\\)\$")


def test_dollar_amounts_are_not_rendered_as_maths():
    """Regression: Streamlit Markdown renders text between two $ signs as a LaTeX formula,
    which garbled replies like 'revenue S$376,771.92, ... net cash flow -S$40,057.65'."""
    at = AppTest.from_file(APP, default_timeout=30).run()
    run(at, "How did we do last quarter?")
    run(at, "How much cash do we have?")
    raw = [e.value for e in [*at.markdown, *at.info, *at.warning, *at.error]]
    assert any("376,771.92" in s for s in raw), "metrics reply not rendered"
    assert [s for s in raw if UNESCAPED_DOLLAR.search(s)] == []


def test_session_opens_with_alerts_and_clock_buttons_move_time():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert "as of 2026-09-30" in shown(at.markdown)[0]
    assert any("Not enough cash for Bill MFI-88120" in e for e in shown(at.error))
    next(b for b in at.sidebar.button if b.label == "+7 days").click().run()
    assert not at.exception
    assert "Simulated today: 2026-10-07" in " ".join(c.value for c in at.caption)
    assert any("Clock moved from 2026-09-30 to 2026-10-07" in i for i in shown(at.info))
    assert any("INV-1061" in i for i in shown(at.info))  # newly overdue, shown as info


def test_what_if_and_recommendations_in_the_app():
    at = AppTest.from_file(APP, default_timeout=30).run()
    run(at, "What if Bayfront pays 3 weeks late?")
    run(at, "How do I fix the cash gap?")
    assert not at.exception
    text = " ".join(shown(at.markdown))
    assert "arrives 21 days later" in text
    assert "Funding need: S$13,025.81" in text
    assert at.metric[0].value == "S$156,526.85"  # what-if changed nothing for real


def test_financing_options_in_the_app():
    at = AppTest.from_file(APP, default_timeout=30).run()
    run(at, "What are my financing options?")
    assert not at.exception
    text = " ".join(shown(at.markdown))
    assert "total cost S$169.52, EIR 16.44%" in text
    assert "Approval is the lender's decision" in text
