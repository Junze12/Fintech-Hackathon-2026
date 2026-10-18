"""Chunk 10 web dashboard: static files served by the API.

There is no JavaScript runtime in the test environment, so the browser-side rules are checked on
the source files themselves:
- R38: the page never parses text as HTML. Every element is built by js/dom.js, which turns
  strings into text nodes; nothing anywhere uses innerHTML and friends, eval, inline handlers or
  outside URLs, and the Content-Security-Policy would block them anyway.
- No maths in the browser: only js/fmt.js (display rounding) and js/charts.js (pixel positions)
  may turn API strings into numbers, so page code can't add up money.
- Every page module calls the endpoints it declares, and those endpoints exist.
Then TestClient checks the served files and headers, the sign-in -> dashboard -> chat ->
confirm flow, and that the poisoned prompt_injection text reaches the page unchanged (raw, for
textContent), never pre-rendered.
"""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="needs the api extra")

from fastapi.testclient import TestClient  # noqa: E402

from copilot.agent.mock_rules import RuleBasedLLM  # noqa: E402
from copilot.api.app import CSP, STATIC, create_app  # noqa: E402
from copilot.api.sessions import SessionStore  # noqa: E402
from copilot.runtime import open_scenario  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
JS = sorted((STATIC / "js").rglob("*.js"))
PAGES = sorted((STATIC / "js" / "pages").glob("*.js"))
ALL = sorted(p for p in STATIC.rglob("*") if p.is_file())
SVG_NS = "http://www.w3.org/2000/svg"  # the only URL allowed: a namespace name, never fetched
NUMBER_HELPERS = {"fmt.js", "charts.js"}


def source(path: Path) -> str:
    return path.read_text("utf-8")


def code_only(text: str) -> str:
    """JS without // and /* */ comments, so rules apply to code, not to explanations."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


def client() -> TestClient:
    return TestClient(
        create_app(SessionStore(), opener=lambda f, r, a: open_scenario(f, r, llm=RuleBasedLLM()))
    )


def signed_in(scenario: str = "cash_crunch", role: str = "owner") -> TestClient:
    c = client()
    assert c.post("/api/session", json={"scenario": scenario, "role": role}).status_code == 200
    return c


# --- Static rules (R38, no external code) -----------------------------------------------------


def test_the_dashboard_files_exist():
    names = {p.relative_to(STATIC).as_posix() for p in ALL}
    assert {"index.html", "styles.css", "js/app.js", "js/dom.js", "js/fmt.js"} <= names
    assert len(PAGES) == 6  # five data pages + the glossary


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.relative_to(STATIC).as_posix())
def test_no_html_parsing_eval_or_outside_urls(path):
    text = source(path).replace(SVG_NS, "")
    if path.suffix == ".js":
        text = code_only(text)
    banned = [
        r"\.innerHTML",
        r"\.outerHTML",
        r"insertAdjacentHTML",
        r"document\.write",
        r"\beval\s*\(",
        r"new\s+Function",
        r"setTimeout\(\s*[\"'`]",
        r"setInterval\(\s*[\"'`]",
        r"javascript:",
        r"https?://",
        r"(?<![:\w])//[a-z0-9.-]+\.[a-z]{2,}",  # protocol-relative URLs
        r"@import",
        r"url\(",
        r"DOMParser",
        r"srcdoc",
    ]
    if path.suffix in (".html", ".svg"):
        banned.append(r"\son[a-z]+\s*=")  # inline event handlers
        banned.append(r'<script(?![^>]* src="js/app\.js")')  # inline scripts
        banned.append(r"<style|\sstyle=")  # inline styles (the CSP blocks them too)
    for pattern in banned:
        assert not re.search(pattern, text, flags=re.I), f"{path.name}: {pattern}"


def test_only_dom_js_creates_elements():
    for path in JS:
        if path.name == "dom.js":
            continue
        text = code_only(source(path))
        assert "createElement" not in text, path.name
        assert "setAttribute" not in text, path.name
        assert "createTextNode" not in text, path.name


def test_dom_helper_only_makes_text_nodes_and_allowlisted_attributes():
    text = code_only(source(STATIC / "js" / "dom.js"))
    assert "document.createTextNode(String(kid))" in text
    assert "Attribute not allowed" in text  # unknown attributes throw instead of being set
    assert re.search(r"\^#\[a-z0-9-\]\*\$", text)  # href only for in-page routes
    for attr in ('"src"', '"srcdoc"', '"style"', '"href"', '"onerror"', '"onclick"'):
        sets = re.findall(r"new Set\(\[(.*?)\]\)", text, flags=re.S)
        assert all(attr not in s for s in sets), attr


def test_links_are_in_page_routes_or_the_two_excel_downloads():
    text = code_only(source(STATIC / "js" / "dom.js"))
    allowed = r"/^\/api\/export\/(statements|forecast)\.xlsx(\?[a-z0-9_=&-]*)?$/"
    assert allowed in text, "the download pattern changed"
    assert r"/^\/api\/upload\/template\/[a-z_]+\.csv$/" in text, "the template pattern changed"
    for path in JS:
        code = code_only(source(path))
        for target in re.findall(r"download\(\s*\"([^\"]+)\"", code):
            assert target in ("/api/export/statements.xlsx", "/api/export/forecast.xlsx"), target
    routes = {r.path for r in create_app().routes}
    assert {"/api/export/statements.xlsx", "/api/export/forecast.xlsx"} <= routes


# --- Glossary (i) icons -----------------------------------------------------------------------


def glossary_keys() -> set[str]:
    text = source(STATIC / "js" / "glossary.js")
    return set(re.findall(r"^\s+([a-z0-9_]+): \{ group:", text, flags=re.M))


def used_terms() -> set[str]:
    """Second argument of every term(...) call and the argument of every info("...") call."""
    keys: set[str] = set()
    for path in JS:
        code = code_only(source(path))
        keys |= set(re.findall(r"\binfo\(\s*\"([a-z0-9_]+)\"\s*\)", code))
        for m in re.finditer(r"(?<!function )\bterm\(", code):
            depth, i = 1, m.end()
            while depth:
                depth += {"(": 1, ")": -1}.get(code[i], 0)
                i += 1
            last = re.search(r",\s*\"([a-z0-9_]+)\"\s*\)$", code[m.start() : i])
            if last:
                keys.add(last.group(1))
            else:
                assert (
                    "TERM_FOR[" in code[m.start() : i] or "DRIVER_TERMS[" in code[m.start() : i]
                ), code[m.start() : i]
        for name in ("TERM_FOR", "DRIVER_TERMS"):
            block = re.search(name + r" = \{(.*?)\};", code, flags=re.S)
            if block:
                keys |= set(re.findall(r":\s*\"([a-z0-9_]+)\"", block.group(1)))
    return keys


def test_every_info_icon_has_a_glossary_entry():
    keys = glossary_keys()
    assert len(keys) >= 40
    used = used_terms()
    assert len(used) >= 40, sorted(used)
    assert used <= keys, sorted(used - keys)


def test_glossary_entries_are_plain_text_in_known_groups():
    text = source(STATIC / "js" / "glossary.js")
    groups = set(re.findall(r'group: "([^"]+)"', text))
    declared_groups = re.search(r"GROUPS = \[(.*?)\]", text).group(1)
    assert groups == set(re.findall(r'"([^"]+)"', declared_groups))
    assert "<" not in text and ">" not in text  # nothing that could look like markup
    assert not re.search(r"S\$\s?\d", text)  # no figures from the books in definitions


def test_the_glossary_page_is_in_the_menu_and_calls_no_api():
    page = STATIC / "js" / "pages" / "glossary.js"
    assert declared(page) == []
    assert "glossary" in re.search(
        r"const PAGES = \[([^\]]*)\]", source(STATIC / "js" / "app.js")
    ).group(1)


def test_storage_only_for_the_theme():
    for path in JS:
        text = code_only(source(path))
        if path.name == "app.js":
            assert set(re.findall(r"localStorage\.\w+\(\"([^\"]+)\"", text)) == {"copilot-theme"}
        else:
            assert "localStorage" not in text, path.name
        assert "sessionStorage" not in text and "indexedDB" not in text, path.name
        assert "document.cookie" not in text, path.name  # the session cookie is HttpOnly anyway


def test_the_page_never_sends_a_role_or_business():
    for path in JS:
        text = code_only(source(path))
        for body in re.findall(r"body:\s*\{([^}]*)\}", text):
            assert "role" not in body or path.name == "app.js" and 'pick("role")' in body
            assert "business" not in body, path.name
    # The only bodies with a role are the two sign-ins: a sample business (POST /api/session)
    # or your own files (POST /api/upload)
    app = code_only(source(STATIC / "js" / "app.js"))
    assert app.count('pick("role")') == 2
    post_with_role = r'api\("(/api/[a-z/]+)", \{ method: "POST", body: \{[^}]*pick\("role"\)'
    posts = re.findall(post_with_role, app)
    assert sorted(posts) == ["/api/session", "/api/upload"]


def test_confirmation_is_typed_by_the_user():
    """The pending card shows the code; nothing in the page sends a confirm message itself."""
    for path in JS:
        text = code_only(source(path))
        assert not re.search(r"[\"'`]confirm\s", text, flags=re.I), path.name
        assert not re.search(r"send\(\s*[`\"']", text.replace("send(q)", "")), path.name


# --- No maths in the browser ------------------------------------------------------------------


@pytest.mark.parametrize(
    "path", [p for p in JS if p.name not in NUMBER_HELPERS], ids=lambda p: p.name
)
def test_page_code_never_turns_api_values_into_numbers(path):
    text = code_only(source(path))
    for pattern in (r"\bNumber\(", r"parseFloat", r"parseInt", r"\bMath\.", r"toFixed", r"BigInt"):
        assert not re.search(pattern, text), f"{path.name}: {pattern}"
    # unary plus as a number conversion, e.g. "= +row.amount" or "(+x"
    assert not re.search(r"[=(,:?]\s*\+\s*[a-z_]", text, flags=re.I), path.name


def test_number_helpers_only_scale_and_round_for_display():
    fmt = code_only(source(STATIC / "js" / "fmt.js"))
    # fmt.js converts to round for display (toFixed), to read a month or day number and in
    # axisMoney (axis ticks the chart chose); it never combines two API values
    for line in fmt.splitlines():
        if "Number(" in line:
            assert re.search(r"toFixed|MONTHS\[|Number\(d\)", line), line
    charts = code_only(source(STATIC / "js" / "charts.js"))
    assert "money(" in charts  # tooltips show the API's string, formatted, not a recomputed value


# --- Pages and endpoints ----------------------------------------------------------------------


def declared(path: Path) -> list[str]:
    m = re.search(r"endpoints:\s*\[([^\]]*)\]", source(path))
    assert m, f"{path.name} declares no endpoints"
    return re.findall(r"\"(/api/[a-z/]+)\"", m.group(1))


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.name)
def test_each_page_fetches_the_endpoints_it_declares(path):
    called = set(re.findall(r"api\(\s*\"(/api/[a-z/]+)\"", code_only(source(path))))
    assert set(declared(path)) == called
    routes = {r.path for r in create_app().routes}
    assert called <= routes


def test_every_dashboard_endpoint_has_a_page():
    shown = {e for p in PAGES for e in declared(p)}
    assert shown == {
        "/api/dashboard",
        "/api/stress",
        "/api/plans",
        "/api/model",
        "/api/valuation",
        "/api/statements",
        "/api/reconciliation",
        "/api/adjustments",
    }


# --- Served files and headers ----------------------------------------------------------------


def test_the_page_is_served_with_a_strict_content_security_policy():
    c = client()
    r = c.get("/")
    assert r.status_code == 200 and "<title>Fintellect</title>" in r.text
    assert r.headers["content-security-policy"] == CSP
    assert "default-src 'none'" in CSP and "script-src 'self'" in CSP and "unsafe" not in CSP
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-content-type-options"] == "nosniff"
    for path in ("js/app.js", "js/pages/overview.js", "styles.css", "favicon.svg"):
        served = c.get(f"/{path}")
        assert served.status_code == 200, path
        assert served.headers["content-security-policy"] == CSP
    assert "javascript" in c.get("/js/app.js").headers["content-type"]


def test_api_routes_win_over_static_files_and_docs_keep_working():
    c = client()
    assert c.get("/api/options").status_code == 200
    assert c.get("/api/dashboard").status_code == 401  # still needs a session
    assert c.get("/api/nothing-here").status_code == 404
    docs = c.get("/docs")
    assert docs.status_code == 200 and "content-security-policy" not in docs.headers


def test_the_session_cookie_stays_http_only_and_scoped_to_the_api():
    r = client().post("/api/session", json={"scenario": "cash_crunch", "role": "owner"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie


# --- Flow: sign in -> dashboard -> chat -> confirm --------------------------------------------


def total(c: TestClient) -> Decimal:
    return Decimal(c.get("/api/dashboard").json()["panels"]["cash"]["data"]["value"]["total"])


def test_sign_in_dashboard_chat_and_typed_confirmation():
    c = signed_in()
    assert total(c) == Decimal("156526.85")
    reply = c.post("/api/chat", json={"message": "Pay bill BL-5048"}).json()
    code = re.search(r"confirm (\d{4})", reply["pending"]).group(1)
    assert "S$61,898.43" in reply["pending"]
    assert c.get("/api/dashboard").json()["pending"] == reply["pending"]  # card survives a reload
    assert total(c) == Decimal("156526.85")  # nothing moves before the user's own confirmation
    done = c.post("/api/chat", json={"message": f"confirm {code}"}).json()
    assert done["pending"] is None
    assert total(c) == Decimal("156526.85") - Decimal("61898.43")


def test_anything_else_cancels_the_pending_payment():
    c = signed_in()
    reply = c.post("/api/chat", json={"message": "Pay bill BL-5048"}).json()
    assert reply["pending"]
    cancelled = c.post("/api/chat", json={"message": "what is my cash?"}).json()
    assert cancelled["pending"] is None and any("Cancelled" in n for n in cancelled["notices"])
    assert total(c) == Decimal("156526.85")


def test_each_page_loads_for_every_role():
    """Every endpoint the pages call answers for every role; a hidden panel says why."""
    for role in ("owner", "staff", "viewer"):
        c = signed_in(role=role)
        for path in sorted({e for p in PAGES for e in declared(p)}):
            r = c.get(path)
            assert r.status_code == 200, (role, path)


# --- R38 on the poisoned fixture --------------------------------------------------------------


def test_poisoned_text_reaches_the_page_raw_for_text_rendering():
    truth = json.loads(
        (ROOT / "data/synthetic/prompt_injection/ground_truth.json").read_text("utf-8")
    )
    poisoned = {p["id"]: p["text"] for p in truth["poisoned"]}
    c = signed_in("prompt_injection")
    seen = {
        "biz-straits": c.get("/api/session").json()["business_name"],
        "a-res": next(
            a["name"]
            for a in c.get("/api/dashboard").json()["panels"]["cash"]["data"]["value"]["accounts"]
            if a["account_id"] == "a-res"
        ),
    }
    st = c.get("/api/statements").json()["data"]["value"]
    seen["fa-van"] = next(a["name"] for a in st["fixed_assets"] if a["id"] == "fa-van")
    seen["TL-20817"] = st["loans"][0]["lender"]
    adj = c.get("/api/adjustments").json()["data"]
    seen["t00158"] = next(
        t["description"] for t in adj["uncategorised_payments"] if t["transaction_id"] == "t00158"
    )
    for key, shown in seen.items():
        # Exactly the imported text: not escaped, wrapped or rendered by the server, so the page's
        # text nodes show it literally (escaping twice would show "&lt;" to the owner).
        assert shown == poisoned[key], key
    assert any("</untrusted>" in s for s in seen.values())  # markup-like text is among them


def test_poisoned_names_are_rendered_by_pages_through_text_nodes_only():
    """Each field above is put on screen by a page module as a child string of h()."""
    pages = {p.name: code_only(source(p)) for p in PAGES}
    app = code_only(source(STATIC / "js" / "app.js"))
    assert 'h("b", {}, me.business_name)' in app
    assert "a.name} ${money(a.balance)}" in pages["overview.js"]
    assert 'h("td", {}, a.name)' in pages["statements.js"]
    assert 'h("span", { class: "cn" }, l.lender)' in pages["statements.js"]
    assert 'h("td", {}, t.description)' in pages["books.js"]


# --- Assistant suggestion chips ---------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["cash_crunch", "concentrated_b2b"])
def test_every_suggestion_chip_is_answered_by_the_demo_assistant(scenario):
    """The chips show what the pages can't (what-ifs, comparisons, a stated financing need).
    Each must work with the rule-based demo on any business, without asking which one."""
    app = source(STATIC / "js" / "app.js")
    block = re.search(r"const SUGGESTIONS = \[(.*?)\];", app, re.S).group(1)
    chips = re.findall(r'"([^"]+)"', block)
    assert len(chips) == 5
    for chip in chips:
        c = signed_in(scenario=scenario)
        reply = c.post("/api/chat", json={"message": chip}).json()
        assert reply["trace"], chip  # answered from a tool, not a clarifying question
        assert reply["trace"][0]["outcome"] == "ok", chip
        # Answer first: the chat shows this line and folds the rest behind "Show details"
        assert reply["text"].startswith("**Short answer:** "), chip


def test_chat_folds_long_replies_but_never_one_that_prepared_an_action():
    app = code_only(source(STATIC / "js" / "app.js"))
    body = re.search(r"function replyBody\(m\) \{(.*?)\n\}", app, re.S).group(1)
    assert 'outcome === "pending"' in body and "if (pending ||" in body
