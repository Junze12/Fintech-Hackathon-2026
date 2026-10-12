"""HTTP API for the web dashboard (chunk 9). Run:  python -m copilot.api

Like the Streamlit app, it only calls agent.handle, the read-only views and the demo clock, so
every read and write still goes through the policy gateway as the signed-in user, and writes
still need the user's own "confirm <code>" message. It adds no capability of its own.

- Demo sign-in (POST /api/session) picks a scenario, role and assistant, the same as the
  Streamlit sidebar (known risk R11: no real authentication). Role and business live in the
  server-side session; no later request can change them (bodies reject unknown fields).
- The browser gets only a random session id in an HttpOnly, SameSite=Strict cookie.
- Imported names (customers, suppliers, accounts) come back as raw text. A frontend must
  render them as text (textContent), never as HTML or Markdown (R37).
- Money is a string in JSON ("148161.41"), never a float.
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from copilot.agent import Session, clock, handle, views
from copilot.agent.claude import has_api_key
from copilot.api.sessions import Entry, SessionStore
from copilot.runtime import SCENARIOS, make_llm, open_scenario
from copilot.schemas import Role

COOKIE = "copilot_session"
MAX_MESSAGE = 2000
ASSISTANTS = ("mock", "claude")
_JSON = TypeAdapter(Any)

# Scenario key (folder name) -> (label shown to the user, folder)
SCENARIO_KEYS: dict[str, tuple[str, Path]] = {
    folder.name: (label, folder) for label, folder in SCENARIOS.items()
}


def allowed_roles() -> list[str]:
    """COPILOT_API_ROLES (e.g. "staff,viewer") hides roles on a hosted demo; default all."""
    raw = os.environ.get("COPILOT_API_ROLES", "owner,staff,viewer")
    names = {r.strip().lower() for r in raw.split(",")}
    return [r.label for r in sorted(Role, reverse=True) if r.label in names]


def to_json(value: Any) -> Any:
    return _JSON.dump_python(value, mode="json")


# --- Request bodies (unknown fields rejected: a smuggled "role" is a 422) -------------------


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignIn(Body):
    scenario: str = Field(description="Scenario key from GET /api/options, e.g. cash_crunch")
    role: str = Field(description="owner, staff or viewer (see GET /api/options)")
    assistant: Literal["mock", "claude"] = "mock"


class ChatIn(Body):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE)


class ClockIn(Body):
    days: int = Field(ge=1, le=7, description="How many simulated days to move forward")


# --- App --------------------------------------------------------------------------------------

Opener = Callable[[Path, Role, str], Session]


def _open(folder: Path, role: Role, assistant: str) -> Session:
    return open_scenario(folder, role, llm=make_llm(assistant))


def create_app(store: SessionStore | None = None, opener: Opener = _open) -> FastAPI:
    sessions = store if store is not None else SessionStore()
    app = FastAPI(
        title="SME Finance Copilot API",
        version="0.1.0",
        description=__doc__,
    )

    @app.middleware("http")
    async def _headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def current(copilot_session: Annotated[str | None, Cookie()] = None) -> Entry:
        entry = sessions.get(copilot_session)
        if entry is None:
            raise HTTPException(401, "Not signed in, or the session expired. Sign in again.")
        return entry

    Current = Annotated[Entry, Depends(current)]

    def describe(entry: Entry) -> dict[str, Any]:
        s = entry.session
        return {
            "business_name": s.business_name,
            "role": s.actor.role.label,
            "assistant": entry.assistant,
            "assistant_name": s.llm.name,
            "today": views.today(s).isoformat(),
            "messages_left": (
                sessions.max_messages - entry.messages_used if entry.assistant == "claude" else None
            ),
        }

    @app.get("/api/options")
    def options() -> dict[str, Any]:
        """What the sign-in form can offer."""
        return {
            "scenarios": [{"key": k, "label": v[0]} for k, v in SCENARIO_KEYS.items()],
            "roles": allowed_roles(),
            "assistants": [a for a in ASSISTANTS if a == "mock" or has_api_key()],
        }

    @app.post("/api/session")
    def sign_in(
        body: SignIn,
        response: Response,
        copilot_session: Annotated[str | None, Cookie()] = None,
    ) -> dict[str, Any]:
        """Demo sign-in: a fresh in-memory sandbox for the chosen scenario and role."""
        if body.scenario not in SCENARIO_KEYS:
            raise HTTPException(422, f"Unknown scenario {body.scenario!r}")
        if body.role not in allowed_roles():
            raise HTTPException(422, f"Role {body.role!r} isn't available")
        if body.assistant == "claude" and not has_api_key():
            raise HTTPException(422, "No API key on the server; use the mock assistant")
        sessions.end(copilot_session)
        session = opener(SCENARIO_KEYS[body.scenario][1], Role[body.role.upper()], body.assistant)
        sid = sessions.create(session, body.assistant)
        response.set_cookie(
            COOKIE,
            sid,
            httponly=True,
            samesite="strict",
            path="/api",
            secure=os.environ.get("COPILOT_COOKIE_SECURE") == "1",
        )
        return describe(sessions.get(sid))

    @app.get("/api/session")
    def who_am_i(entry: Current) -> dict[str, Any]:
        return describe(entry)

    @app.delete("/api/session")
    def sign_out(
        response: Response, copilot_session: Annotated[str | None, Cookie()] = None
    ) -> dict[str, bool]:
        sessions.end(copilot_session)
        response.delete_cookie(COOKIE, path="/api")
        return {"signed_out": True}

    @app.get("/api/dashboard")
    def dashboard(entry: Current) -> dict[str, Any]:
        """Every panel through the policy gateway as the signed-in user. Each panel is
        {ok, message, data}; one failing panel doesn't stop the others."""
        with entry.lock:
            s = entry.session
            panels = {
                name: {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}
                for name, r in views.dashboard_panels(s).items()
            }
            start, end = views.last_full_quarter(s)
            return {
                "today": views.today(s).isoformat(),
                "metrics_period": {"start": start.isoformat(), "end": end.isoformat()},
                "pending": views.pending_panel(s),
                "panels": panels,
            }

    @app.get("/api/statements")
    def statements(
        entry: Current,
        period: Literal["month", "quarter", "ytd", "last_12_months"] = "month",
        month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
        statement: Literal["all", "pnl", "balance_sheet", "cash_flow"] = "all",
        view: Literal["with_adjustments", "as_imported"] = "with_adjustments",
    ) -> dict[str, Any]:
        """Accrual P&L, balance sheet and cash flow (chunk 12), through the policy gateway as
        the signed-in user. {ok, message, data} like a dashboard panel."""
        with entry.lock:
            r = views.statements(entry.session, period, month, statement, view)
            return {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}

    @app.get("/api/adjustments")
    def adjustments(entry: Current) -> dict[str, Any]:
        """The owner's recorded adjustments and saved forecast assumptions (chunk 13), read-only.
        Creating or undoing one goes through chat, where the owner confirms it."""
        with entry.lock:
            r = views.adjustments(entry.session)
            return {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}

    @app.post("/api/chat")
    def chat(body: ChatIn, entry: Current) -> dict[str, Any]:
        """One user message through the agent. A write comes back as `pending`; it runs only
        if the user's next message is the exact "confirm <code>" it names."""
        with entry.lock:
            if entry.assistant == "claude":
                if entry.messages_used >= sessions.max_messages:
                    raise HTTPException(
                        429, "Message limit for this demo session reached. Sign in again."
                    )
                entry.messages_used += 1
            reply = handle(body.message, entry.session)
            return {
                "text": reply.text,
                "notices": list(reply.notices),
                "pending": reply.pending_prompt,
                "trace": [{"tool": t.tool, "outcome": t.outcome} for t in reply.trace],
            }

    @app.post("/api/clock/advance")
    def advance_clock(body: ClockIn, entry: Current) -> dict[str, Any]:
        """Move the simulated clock: the scripted world plays out and confirmed scheduled
        payments run (guards re-checked). Not available to the assistant."""
        with entry.lock:
            return to_json(clock.advance(entry.session, body.days))

    return app


app = create_app()
