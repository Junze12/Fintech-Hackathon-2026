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
- The web dashboard (chunk 10) is served from static/ at "/" under a strict
  Content-Security-Policy: same-origin scripts, styles and requests only.
"""

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from copilot.agent import Session, clock, handle, views
from copilot.agent.claude import has_api_key
from copilot.api import export, upload
from copilot.api.sessions import Entry, SessionStore
from copilot.runtime import SCENARIOS, AdapterError, make_llm, open_scenario, read_folder
from copilot.schemas import Role

COOKIE = "copilot_session"
MAX_MESSAGE = 2000
ASSISTANTS = ("mock", "claude")
_JSON = TypeAdapter(Any)
STATIC = Path(__file__).parent / "static"
# For the web dashboard: nothing from other origins, no inline script or style, no framing.
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
_DOCS = ("/api", "/docs", "/redoc", "/openapi.json")  # FastAPI's /docs page loads its own CDN

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


class Upload(Body):
    files: dict[str, str] = Field(
        max_length=len(upload.FILES), description="File name -> CSV text (see upload_files)"
    )
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
        title="Fintellect API",
        version="0.1.0",
        description=__doc__,
    )

    @app.middleware("http")
    async def _headers(request: Request, call_next):
        if request.url.path == "/api/upload" and request.method == "POST":
            # Refuse a large body before it is read and parsed (R54).
            size = request.headers.get("content-length", "")
            if not size.isdigit() or int(size) > upload.MAX_BODY_BYTES:
                return JSONResponse({"detail": "The upload is larger than 5 MB."}, 413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if not request.url.path.startswith(_DOCS):
            response.headers["Content-Security-Policy"] = CSP
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def current(copilot_session: Annotated[str | None, Cookie()] = None) -> Entry:
        entry = sessions.get(copilot_session)
        if entry is None:
            raise HTTPException(401, "Not signed in, or the session expired. Sign in again.")
        return entry

    Current = Annotated[Entry, Depends(current)]

    def cached(entry: Entry, request: Request, make: Callable[[], dict[str, Any]]):
        """Same request in the same session -> the stored result (reads are deterministic and the
        data only changes through chat or the clock, which clear the cache)."""
        key = f"{request.url.path}?{urlencode(sorted(request.query_params.multi_items()))}"
        with entry.lock:
            return entry.remember(key, make)

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
            "upload_files": upload.file_list(),
        }

    def check_actor(role: str, assistant: str) -> None:
        if role not in allowed_roles():
            raise HTTPException(422, f"Role {role!r} isn't available")
        if assistant == "claude" and not has_api_key():
            raise HTTPException(422, "No API key on the server; use the mock assistant")

    def start(response: Response, old: str | None, session: Session, assistant: str) -> Entry:
        """Replace any earlier session of this browser and hand over the new session's cookie."""
        sessions.end(old)
        sid = sessions.create(session, assistant)
        response.set_cookie(
            COOKIE,
            sid,
            httponly=True,
            samesite="strict",
            path="/api",
            secure=os.environ.get("COPILOT_COOKIE_SECURE") == "1",
        )
        return sessions.get(sid)

    @app.post("/api/session")
    def sign_in(
        body: SignIn,
        response: Response,
        copilot_session: Annotated[str | None, Cookie()] = None,
    ) -> dict[str, Any]:
        """Demo sign-in: a fresh in-memory sandbox for the chosen scenario and role."""
        if body.scenario not in SCENARIO_KEYS:
            raise HTTPException(422, f"Unknown scenario {body.scenario!r}")
        check_actor(body.role, body.assistant)
        session = opener(SCENARIO_KEYS[body.scenario][1], Role[body.role.upper()], body.assistant)
        return describe(start(response, copilot_session, session, body.assistant))

    @app.post("/api/upload")
    def upload_data(
        body: Upload,
        response: Response,
        copilot_session: Annotated[str | None, Cookie()] = None,
    ) -> dict[str, Any]:
        """Sign in with your own CSV files: a fresh in-memory sandbox for this session only.
        The files are loaded through the CSV adapter from a temporary folder that is deleted
        straight after (R54). Returns the session plus an import summary."""
        check_actor(body.role, body.assistant)
        files = body.files
        if problem := upload.check(files):
            raise HTTPException(422, problem)
        with tempfile.TemporaryDirectory(prefix="copilot-upload-") as tmp:
            folder = Path(tmp)
            for name, text in files.items():
                (folder / name).write_text(text, encoding="utf-8", newline="")
            try:
                imported = read_folder(folder)
            except AdapterError as exc:
                raise HTTPException(422, str(exc).replace(str(folder), "the upload")) from None
            session = opener(folder, Role[body.role.upper()], body.assistant)
        entry = start(response, copilot_session, session, body.assistant)
        return {**describe(entry), "import": upload.summary(imported, set(files))}

    @app.get("/api/upload/template/{name}")
    def upload_template(name: str) -> Response:
        """An empty CSV with the right headers for one of the upload files."""
        if name not in upload.FILES:
            raise HTTPException(404, "No such file")
        return Response(
            upload.template_csv(name),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

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
    def dashboard(entry: Current, request: Request) -> dict[str, Any]:
        """Every panel through the policy gateway as the signed-in user. Each panel is
        {ok, message, data}; one failing panel doesn't stop the others."""

        def make() -> dict[str, Any]:
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

        return cached(entry, request, make)

    @app.get("/api/statements")
    def statements(
        entry: Current,
        request: Request,
        period: Literal["month", "quarter", "ytd", "last_12_months"] = "month",
        month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
        statement: Literal["all", "pnl", "balance_sheet", "cash_flow"] = "all",
        view: Literal["with_adjustments", "as_imported"] = "with_adjustments",
    ) -> dict[str, Any]:
        """Accrual P&L, balance sheet and cash flow (chunk 12), through the policy gateway as
        the signed-in user. {ok, message, data} like a dashboard panel."""

        def make() -> dict[str, Any]:
            r = views.statements(entry.session, period, month, statement, view)
            return {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}

        return cached(entry, request, make)

    def download(entry: Entry, kind: str, tail: str, r: Any, build) -> Response:
        """An Excel file built from a gateway result, or the gateway's refusal as a 403."""
        if not r.ok:
            raise HTTPException(403, r.message)
        body = build(entry.session.business_name, to_json(r.data)["value"])
        name = f"{entry.session.actor.business_id}-{kind}{tail}.xlsx"
        return Response(
            body,
            media_type=export.CONTENT_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get("/api/export/statements.xlsx")
    def export_statements(
        entry: Current,
        period: Literal["month", "quarter", "ytd", "last_12_months"] = "month",
        month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
        view: Literal["with_adjustments", "as_imported"] = "with_adjustments",
    ) -> Response:
        """The statements shown on the Statements page as an Excel workbook (same gateway read,
        same parameters; nothing recomputed)."""
        with entry.lock:
            r = views.statements(entry.session, period, month, "all", view)
        tail = f"-{period}-{r.data.value.end.isoformat()}" if r.ok else ""
        return download(entry, "statements", tail, r, export.statements_workbook)

    @app.get("/api/export/forecast.xlsx")
    def export_forecast(entry: Current) -> Response:
        """The 13-week forecast shown on the Overview as an Excel workbook."""
        with entry.lock:
            r = views.forecast(entry.session)
        tail = f"-{r.data.value.as_of.isoformat()}" if r.ok else ""
        return download(entry, "forecast", tail, r, export.forecast_workbook)

    @app.get("/api/model")
    def financial_model(
        entry: Current,
        request: Request,
        case: Literal["all", "worst", "expected", "best"] = "all",
        view: Literal["annual", "monthly"] = "annual",
        year: Annotated[int, Query(ge=1, le=3)] = 1,
    ) -> dict[str, Any]:
        """3-year model in Worst / Expected / Best cases (chunk 14a), drivers from the books,
        through the policy gateway as the signed-in user. The monthly view is for one case."""

        def make() -> dict[str, Any]:
            r = views.financial_model(entry.session, case, view, year)
            return {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}

        return cached(entry, request, make)

    @app.get("/api/valuation")
    def valuation(
        entry: Current,
        request: Request,
        case: Literal["all", "worst", "expected", "best"] = "all",
        discount_rate_pct: Annotated[str | None, Query(pattern=r"^\d{1,2}(\.\d{1,2})?$")] = None,
        terminal_growth_pct: Annotated[str | None, Query(pattern=r"^-?\d(\.\d{1,2})?$")] = None,
        ebitda_multiple: Annotated[str | None, Query(pattern=r"^\d{1,2}(\.\d{1,2})?$")] = None,
        owner_salary_monthly: Annotated[str | None, Query(pattern=r"^\d{1,6}(\.\d{1,2})?$")] = None,
    ) -> dict[str, Any]:
        """Break-even per case and the estimated value (chunk 14b) through the policy gateway
        as the signed-in user: break-even line points per case, valuation card (inputs with
        sources, DCF, multiple, bridge) and sensitivity rows. Read-only; the valuation inputs
        are query parameters and nothing is saved. Out-of-range inputs give ok false."""

        def make() -> dict[str, Any]:
            r = views.valuation(
                entry.session,
                case,
                discount_rate_pct,
                terminal_growth_pct,
                ebitda_multiple,
                owner_salary_monthly,
            )
            return {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}

        return cached(entry, request, make)

    @app.get("/api/stress")
    def stress_test(
        entry: Current,
        request: Request,
        shock_amount: Annotated[str, Query(pattern=r"^\d{1,8}(\.\d{1,2})?$")] = "0",
        shock_date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        target_pct: Annotated[int, Query(ge=80, le=99)] = 95,
        best_plan: bool = True,
    ) -> dict[str, Any]:
        """Cash-shock stress test (chunk 16a) through the policy gateway as the signed-in user:
        survival, P10/P50/P90 per day, survival curve, gap bridge, headline. The shock is this
        view's input (a what-if the viewer types), so it is a query parameter; nothing is saved.
        best_plan=false skips the options search behind the headline (~2 s); every other field
        is the same. The dashboard takes the best plan from /api/plans instead.
        """

        def make() -> dict[str, Any]:
            r = views.stress_test(entry.session, shock_amount, shock_date, target_pct, best_plan)
            return {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}

        return cached(entry, request, make)

    @app.get("/api/plans")
    def plans(
        entry: Current,
        request: Request,
        target_pct: Annotated[int, Query(ge=80, le=99)] = 95,
        shock_amount: Annotated[str, Query(pattern=r"^\d{1,8}(\.\d{1,2})?$")] = "0",
        shock_date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        chase_on_time_pct: Annotated[int, Query(ge=0, le=100)] = 50,
        customer_loss_pct: Annotated[int, Query(ge=0, le=100)] = 0,
    ) -> dict[str, Any]:
        """Options under uncertainty (chunk 16b) through the policy gateway as the signed-in
        user: options table (ordered rows), frontier (cost, survival % points), cost bridge,
        cash with the best plan and credit-line use per day (P10/P50/P90). Read-only: nothing
        is applied or saved; the viewer's assumptions are query parameters."""

        def make() -> dict[str, Any]:
            r = views.options_comparison(
                entry.session,
                target_pct,
                shock_amount,
                shock_date,
                chase_on_time_pct,
                customer_loss_pct,
            )
            return {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}

        return cached(entry, request, make)

    @app.get("/api/reconciliation")
    def reconciliation(
        entry: Current,
        request: Request,
        min_severity: Annotated[str, Query(pattern=r"^(high|medium|low)$")] = "low",
    ) -> dict[str, Any]:
        """Reconciliation exceptions (chunk 15) through the policy gateway as the signed-in user:
        each with kind, severity, S$ at stake, documents and transactions involved, reason and
        next step; plus counts and S$ by severity. Read-only: fixes go through chat."""

        def make() -> dict[str, Any]:
            r = views.reconciliation(entry.session, min_severity)
            return {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}

        return cached(entry, request, make)

    @app.get("/api/adjustments")
    def adjustments(entry: Current, request: Request) -> dict[str, Any]:
        """The owner's recorded adjustments and saved forecast assumptions (chunk 13), read-only.
        Creating or undoing one goes through chat, where the owner confirms it."""

        def make() -> dict[str, Any]:
            r = views.adjustments(entry.session)
            return {"ok": r.ok, "message": r.message, "data": to_json(r.data) if r.ok else None}

        return cached(entry, request, make)

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
            entry.cache.clear()
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
            entry.cache.clear()
            return to_json(clock.advance(entry.session, body.days))

    # Last, so every /api route above wins over a static file of the same name
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
    return app


app = create_app()
