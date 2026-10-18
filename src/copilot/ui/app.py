"""Minimal Streamlit chat for Fintellect (SME Finance Copilot).

Run:  streamlit run src/copilot/ui/app.py
It only calls agent.handle(...), the read-only views and the demo clock (agent.clock).
Demo sign-in: pick a business and a user in the sidebar; changing either starts a fresh
in-memory sandbox. "+1 day" / "+7 days" move the simulated clock: the scripted world plays
out (customers pay, bills and payroll go out) and the owner's scheduled payments run.
Messages from the system (alerts, clock reports, payment results) are written by code, not
by the assistant.
"""

from __future__ import annotations

import streamlit as st

from copilot.agent import clock, handle, views
from copilot.agent.claude import has_api_key
from copilot.runtime import SCENARIOS, make_llm, open_scenario
from copilot.schemas import Role, sgd

USERS = {"Owner": Role.OWNER, "Staff": Role.STAFF, "Viewer": Role.VIEWER}
ASSISTANTS = {"Claude": "claude", "Rule-based demo (no API key)": "mock"}
ALERTS_SHOWN = 5
OPENING_ALERTS = 3

st.set_page_config(page_title="Fintellect", layout="wide")


def start(business: str, user: str, assistant: str) -> None:
    llm = make_llm(ASSISTANTS[assistant])
    st.session_state.session = open_scenario(SCENARIOS[business], USERS[user], llm=llm)
    st.session_state.key = (business, user, assistant)
    st.session_state.chat = []
    refresh_panels()
    alerts = st.session_state.panels["alert"] or []
    today = st.session_state.panels["today"].isoformat()
    opening = (
        f"Here is what needs your attention as of {today}:"
        if alerts
        else f"No cash alerts as of {today}."
    )
    st.session_state.chat.append(
        {"role": "assistant", "text": opening, "alerts": alerts[:OPENING_ALERTS]}
    )


def advance_clock(days: int) -> None:
    report = clock.advance(st.session_state.session, days)
    notices = [report.message]
    if report.ok:
        for event in report.world:
            if event.outcome == "blocked":
                notices.append(
                    f"Bounced on {event.date.isoformat()}: {event.description} "
                    f"({sgd(-event.amount)}), {event.reason}."
                )
        for payment in report.payments:
            text = f"{payment.description}: {sgd(payment.amount)} on {payment.date.isoformat()}"
            notices.append(
                f"Scheduled payment made. {text}."
                if payment.outcome == "executed"
                else f"Scheduled payment stopped ({payment.outcome}). {text}: {payment.reason}."
            )
    st.session_state.chat.append(
        {"role": "assistant", "text": "", "notices": tuple(notices), "alerts": report.new_alerts}
    )
    refresh_panels()


def show_alert(alert, where=st) -> None:
    show = {"critical": where.error, "warning": where.warning}.get(alert.severity, where.info)
    show(md(alert.message))


def refresh_panels() -> None:
    session = st.session_state.session
    st.session_state.panels = {
        "today": views.today(session),
        "cash": views.cash_panel(session),
        "alert": views.alert_panel(session),
        "pending": views.pending_panel(session),
    }


def md(text: str) -> str:
    """Show $ and [ literally: Streamlit Markdown treats text between two $ signs as a maths
    formula, and "![x](address)" as an image it loads at once. Imported names and replies must
    never make the browser fetch an outside address."""
    return text.replace("$", r"\$").replace("[", r"\[")


# --- Sidebar: demo sign-in and panels -------------------------------------------

with st.sidebar:
    st.header("Demo sign-in")
    business = st.selectbox("Business", list(SCENARIOS))
    user = st.selectbox("Signed in as", list(USERS))
    key_found = has_api_key()
    choices = list(ASSISTANTS) if key_found else list(ASSISTANTS)[1:]
    assistant = st.selectbox("Assistant", choices)
    if not key_found:
        st.caption("No API key found (.env at the repo root), so the rule-based demo is used.")
    if st.session_state.get("key") != (business, user, assistant):
        start(business, user, assistant)
    if st.button("Reset sandbox"):
        start(business, user, assistant)

    session = st.session_state.session
    panels = st.session_state.panels
    st.caption(f"Assistant: {session.llm.name}")
    st.caption(f"Simulated today: {panels['today'].isoformat()}")
    one_day, one_week = st.columns(2)
    if one_day.button("+1 day"):
        advance_clock(1)
        st.rerun()
    if one_week.button("+7 days"):
        advance_clock(7)
        st.rerun()

    st.subheader("Cash")
    cash = panels["cash"]
    if cash is None:
        st.write("Unavailable")
    else:
        st.metric("Total", sgd(cash.total))
        for account in cash.accounts:
            st.write(md(f"{account.name}: {sgd(account.balance)}"))

    st.subheader("Alerts")
    alerts = panels["alert"]
    if alerts is None:
        st.write("Unavailable")
    elif not alerts:
        st.success("No cash alerts in the next 13 weeks")
    else:
        for alert in alerts[:ALERTS_SHOWN]:
            show_alert(alert)
        if len(alerts) > ALERTS_SHOWN:
            st.caption(f"{len(alerts) - ALERTS_SHOWN} more: ask 'any alerts?'")

    st.subheader("Waiting for your confirmation")
    st.write(md(panels["pending"] or "Nothing pending"))

# --- Chat -----------------------------------------------------------------------

st.title("Fintellect")
st.caption(md(f"{session.business_name} · signed in as {user}"))

for entry in st.session_state.chat:
    with st.chat_message(entry["role"]):
        if entry["text"]:
            st.markdown(md(entry["text"]))
        for notice in entry.get("notices", ()):
            st.info(md(notice))
        for alert in entry.get("alerts", ()):
            show_alert(alert)
        if entry.get("pending"):
            st.warning(md(entry["pending"]))
        if entry.get("trace"):
            st.caption("Tools: " + ", ".join(f"{t.tool} ({t.outcome})" for t in entry["trace"]))

prompt = st.chat_input("Ask about cash, alerts, what's coming up, or 'pay bill BL-5048'")
if prompt:
    reply = handle(prompt, session)
    st.session_state.chat.append({"role": "user", "text": prompt})
    st.session_state.chat.append(
        {
            "role": "assistant",
            "text": reply.text,
            "notices": reply.notices,
            "pending": reply.pending_prompt,
            "trace": reply.trace,
        }
    )
    refresh_panels()
    st.rerun()
