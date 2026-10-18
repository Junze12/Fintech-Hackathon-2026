// App shell: sign-in, sidebar pages, top bar with the simulated clock, and the chat dock.
// Every number on screen comes from /api; pages only pick, format and draw (no maths here).
import { api, whenSignedOut } from "./api.js";
import { h, icon, mount, s } from "./dom.js";
import { cap, date, money, signed } from "./fmt.js";
import { badge, more, SEVERITY_TONE, table } from "./ui.js";
import overview from "./pages/overview.js";
import plan from "./pages/plan.js";
import outlook from "./pages/outlook.js";
import statements from "./pages/statements.js";
import books from "./pages/books.js";
import glossary from "./pages/glossary.js";

const PAGES = [overview, plan, outlook, statements, books, glossary];
const app = document.getElementById("app");
const side = document.getElementById("side");
const main = document.getElementById("main");
const dock = document.getElementById("dock");

const state = { me: null, page: null, clock: null, chat: [], pending: null, busy: false, renderId: 0 };

// --- Theme (a per-viewer convenience; storage may be unavailable) ---------------------------
const THEMES = ["auto", "light", "dark"];
function readTheme() {
  try {
    return localStorage.getItem("copilot-theme") || "auto";
  } catch {
    return "auto";
  }
}
function applyTheme(theme) {
  if (theme === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
}
function cycleTheme() {
  const next = THEMES[(THEMES.indexOf(readTheme()) + 1) % THEMES.length];
  try {
    localStorage.setItem("copilot-theme", next);
  } catch {
    /* not remembered */
  }
  applyTheme(next);
  renderSide();
}
applyTheme(readTheme());

/** Fintellect's mark: a rising line ending in a point of insight (same drawing as favicon.svg). */
function logo(size = 30) {
  return s(
    "svg",
    { class: "logo", viewBox: "0 0 32 32", width: size, height: size, "aria-hidden": "true" },
    s("rect", { class: "logo-bg", width: 32, height: 32, rx: 9 }),
    s("path", { class: "logo-ln", d: "M8 21.5l5.2-5.6 3.8 3.1 3.6-4.4" }),
    s("circle", { class: "logo-dot", cx: 23.9, cy: 10.6, r: 2.4 }),
  );
}

// --- Sign-in ---------------------------------------------------------------------------------
const ROLE_TEXT = {
  owner: ["Owner", "Everything, including payments and loan applications (each needs a confirmation code)"],
  staff: ["Staff", "Read, draft reminders and adjustments, pre-fill applications"],
  viewer: ["Viewer", "Read-only: analysis, forecasts, alerts and comparisons"],
};

async function showSignIn(message) {
  state.me = null;
  app.classList.add("signed-out");
  side.replaceChildren();
  dock.replaceChildren();
  let options;
  try {
    options = await api("/api/options");
  } catch (e) {
    mount(main, h("p", { class: "err" }, e.message));
    return;
  }
  const err = h("p", { class: "err", role: "alert" }, message || "");
  const radios = (name, items, first) =>
    h(
      "fieldset",
      { class: "users" },
      h("legend", {}, name === "scenario" ? "Business" : name === "role" ? "Sign in as" : "Assistant"),
      items.map(([value, title, sub], i) =>
        h("label", { class: "user" }, h("input", { type: "radio", name, value, checked: i === first }), h("div", {}, h("b", {}, title), sub ? h("small", {}, sub) : null)),
      ),
    );
  // Bring your own data: CSV files read in the browser and sent as text (known risk R54)
  const picker = h("input", { type: "file", multiple: true, accept: ".csv,text/csv", "aria-label": "Your CSV files", on: { change: () => chosen.replaceChildren(...[...picker.files].map((f) => h("li", {}, f.name))) } });
  const chosen = h("ul", { class: "chosen" });
  const upload = h(
    "div",
    { class: "upload", hidden: true },
    h("label", { class: "field" }, h("span", {}, "Choose your CSV files (at least business.csv)"), picker),
    chosen,
    h(
      "details",
      {},
      h("summary", {}, "File formats and templates"),
      h("p", { class: "note" }, "One file per kind of record; the first row holds the column names in the template. Dates as YYYY-MM-DD or DD/MM/YYYY, amounts in SGD. Files are kept in memory for this session only."),
      h("ul", { class: "formats" }, options.upload_files.map((f) => h("li", {}, h("a", { href: `/api/upload/template/${f.name}`, download: "" }, f.name), f.required ? " (required)" : "", `: ${f.unlocks}`))),
    ),
  );
  const form = h(
    "form",
    { class: "card", on: { submit: (ev) => signIn(ev, form, err, picker), change: () => (upload.hidden = form.querySelector('input[name="scenario"]:checked')?.value !== "upload") } },
    h("h1", {}, "Demo sign-in"),
    h("p", { class: "note" }, "Each sign-in opens a fresh sandbox. Role and business are fixed for the session and can't be changed from the page or the chat."),
    radios("scenario", [...options.scenarios.map((x) => [x.key, x.label]), ["upload", "Your own data", "Upload your CSV files"]], 0),
    upload,
    radios("role", options.roles.map((r) => [r, ...(ROLE_TEXT[r] || [r])]), 0),
    radios(
      "assistant",
      options.assistants.map((a) => (a === "claude" ? ["claude", "Claude", "AI model; limited messages per session"] : ["mock", "Rule-based demo", "No AI model; fixed phrases"])),
      0,
    ),
    err,
    h("button", { class: "btn pri", type: "submit" }, "Sign in"),
  );
  const intro = h(
    "section",
    { class: "intro" },
    h("div", { class: "brand" }, logo(36), "Fintellect"),
    h("p", { class: "tag" }, "An AI finance copilot for small businesses. It reads your books, warns you before cash runs short, and finds the cheapest way to close the gap."),
    h(
      "ul",
      { class: "points" },
      [
        ["chart", "Understand your numbers", "Margins, cash trend, statements and ageing, built from your own books"],
        ["alert", "See cash problems early", "A 13-week forecast, alerts and 2,000 simulated payment timings"],
        ["plan", "Compare your options", "Chase, delay or borrow, with full costs. Nothing runs until you confirm it"],
      ].map(([ic, title, text]) => h("li", {}, h("span", { class: "pt-ic" }, icon(ic, 18)), h("div", {}, h("b", {}, title), h("span", {}, text)))),
    ),
    h("p", { class: "fine" }, "Demo: the sample businesses are fictional (synthetic data)."),
  );
  mount(main, h("div", { class: "login" }, h("div", { class: "login-in" }, intro, form)));
}

async function signIn(ev, form, err, picker) {
  ev.preventDefault();
  const pick = (name) => (form.querySelector(`input[name="${name}"]:checked`) || {}).value;
  err.textContent = "";
  try {
    if (pick("scenario") === "upload") {
      if (!picker.files.length) throw new Error("Choose your CSV files first (at least business.csv).");
      const files = Object.fromEntries(await Promise.all([...picker.files].map(async (f) => [f.name, await f.text()])));
      const res = await api("/api/upload", { method: "POST", body: { files, role: pick("role"), assistant: pick("assistant") } });
      mount(main, h("div", { class: "login" }, importSummary(res)));
      return;
    }
    await api("/api/session", { method: "POST", body: { scenario: pick("scenario"), role: pick("role"), assistant: pick("assistant") } });
    enter();
  } catch (e) {
    err.textContent = e.message;
  }
}

// A fresh page load per sign-in: pages keep their picks (month, what-if inputs) in module
// variables, which must not carry over to another business. The cookie restores the session.
function enter() {
  location.hash = "";
  location.reload();
}

/** What the upload loaded, rejected and lacks; the session already exists. */
function importSummary(res) {
  const imp = res.import;
  const list = (title, items, open) => (items.length ? h("details", { open }, h("summary", {}, title), h("ul", { class: "steps" }, items)) : null);
  return h(
    "section",
    { class: "card" },
    h("h1", {}, "Data loaded"),
    h("p", { class: "note" }, `${res.business_name}: today in the sandbox is ${date(res.today)} (your latest bank transaction). Kept in memory for this session only.`),
    table(
      ["File", { text: "Rows loaded", cls: "n" }, { text: "Rows rejected", cls: "n" }],
      imp.files.map((f) => h("tr", {}, h("td", {}, f.name), h("td", { class: "n" }, String(f.loaded)), h("td", { class: `n ${f.rejected ? "neg" : ""}` }, String(f.rejected)))),
    ),
    list(
      imp.rejected_total > imp.rejected_rows.length ? `Rejected rows (first ${imp.rejected_rows.length} of ${imp.rejected_total})` : `Rejected rows (${imp.rejected_total})`,
      imp.rejected_rows.map((r) => h("li", {}, `${r.file} line ${r.line}: ${r.reason}`)),
      true,
    ),
    list(`Not provided (${imp.missing.length})`, imp.missing.map((m) => h("li", {}, h("b", {}, m.name), `: ${m.unlocks}`)), false),
    list(`Warnings (${imp.warnings.length})`, imp.warnings.map((w) => h("li", {}, w)), false),
    h("button", { class: "btn pri", type: "button", on: { click: enter } }, "Continue to dashboard"),
  );
}

async function signOut() {
  try {
    await api("/api/session", { method: "DELETE" });
  } finally {
    showSignIn();
  }
}

whenSignedOut(() => showSignIn("Your session ended. Please sign in again."));

// --- Shell ------------------------------------------------------------------------------------
function currentPage() {
  const key = location.hash.replace("#", "");
  return PAGES.find((p) => p.key === key) || PAGES[0];
}

function initials(name) {
  return (name.match(/\b[A-Za-z]/g) || []).slice(0, 2).join("").toUpperCase() || "?";
}

function renderSide() {
  if (!state.me) return;
  const page = currentPage();
  const me = state.me;
  mount(
    side,
    h("div", { class: "brand" }, logo(30), "Fintellect"),
    h("div", { class: "biz" }, h("span", { class: "av" }, initials(me.business_name)), h("div", {}, h("b", {}, me.business_name), h("small", {}, `${ROLE_TEXT[me.role] ? ROLE_TEXT[me.role][0] : me.role} · S$`))),
    h("div", { class: "sec" }, "Pages"),
    PAGES.filter((p) => p !== glossary).map(navLink),
    h("div", { class: "grow" }),
    h("div", { class: "sample" }, h("b", {}, "Sandbox. "), "Sample businesses are fictional; uploaded data stays in this session only. Every figure is calculated on the server from the books; the page only displays it."),
    h("button", { class: "nav", type: "button", on: { click: cycleTheme } }, icon("sun", 19), h("span", {}, `Theme: ${cap(readTheme())}`)),
    h("button", { class: "nav", type: "button", on: { click: () => setDock(true) } }, icon("chat", 19), h("span", {}, "Assistant")),
    navLink(glossary),
    h("button", { class: "nav", type: "button", on: { click: signOut } }, icon("out", 19), h("span", {}, "Sign out")),
  );
  function navLink(p) {
    return h("a", { class: "nav", href: `#${p.key}`, "aria-current": p === page ? "page" : null, on: { click: () => app.classList.remove("open") } }, icon(p.icon, 19), h("span", {}, p.nav));
  }
}

function topbar(page) {
  return h(
    "header",
    { class: "top" },
    h("button", { class: "menu", type: "button", "aria-label": "Open menu", on: { click: () => app.classList.add("open") } }, icon("menu", 20)),
    h("div", { class: "titles" }, h("h1", {}, page.title), h("p", {}, page.subtitle)),
    h(
      "div",
      { class: "ctl" },
      h("span", { class: "today" }, h("small", {}, "Today (simulated)"), h("b", {}, date(state.me.today))),
      h("button", { class: "btn", type: "button", on: { click: advanceClock }, title: "Move the sandbox clock forward a week: customers pay, bills go out, alerts re-run" }, icon("clock", 16), "Advance 7 days"),
    ),
  );
}

function clockCard() {
  const c = state.clock;
  if (!c) return null;
  const rows = [
    ...(c.world || []).map((e) => h("div", { class: "ev" }, h("span", { class: "d" }, date(e.date)), h("span", {}, e.description), h("span", { class: "n" }, signed(e.amount)), badge(e.outcome === "executed" ? "neu" : "warn", e.outcome))),
    ...(c.payments || []).map((p) => h("div", { class: "ev" }, h("span", { class: "d" }, date(p.date)), h("span", {}, p.description || p.payee_name || "Scheduled payment"), h("span", { class: "n" }, money(p.amount)), badge(p.outcome === "executed" ? "pos" : "neg", p.outcome))),
  ];
  return h(
    "section",
    { class: "card clock-card" },
    h("div", { class: "card-h" }, h("div", { class: "t" }, h("h2", {}, "What happened this week"), h("p", {}, c.message)), h("button", { class: "btn ghost sm", type: "button", on: { click: () => { state.clock = null; render(); } } }, "Dismiss")),
    rows.length ? h("div", {}, rows) : h("p", { class: "note" }, "No money moved."),
    (c.new_alerts || []).length
      ? h("div", { class: "alerts", style: { "margin-top": "12px" } }, c.new_alerts.map((a) => h("div", { class: "alert" }, badge(SEVERITY_TONE[a.severity] || "neu", a.severity), h("div", {}, h("b", {}, a.title), h("span", {}, a.message)))))
      : null,
  );
}

async function advanceClock() {
  try {
    state.clock = await api("/api/clock/advance", { method: "POST", body: { days: 7 } });
    state.me = await api("/api/session");
  } catch (e) {
    state.clock = { message: e.message, world: [], payments: [], new_alerts: [] };
  }
  renderSide();
  render();
}

/** Draw the current page; a newer call wins if an older fetch finishes late. */
async function render() {
  if (!state.me) return;
  const page = currentPage();
  const id = ++state.renderId;
  const body = h("div", { class: "stack" });
  mount(main, topbar(page), h("div", { class: "stack" }, clockCard(), body));
  try {
    await page.render(body, { me: state.me, setPending, isCurrent: () => id === state.renderId });
  } catch (e) {
    if (id === state.renderId) mount(body, h("div", { class: "pmsg", role: "alert" }, e.message));
  }
}

// --- Chat dock --------------------------------------------------------------------------------
// Questions the pages can't answer by themselves: what-ifs, comparisons and a financing need the
// owner states. Fixed text on purpose: a chip is sent as the user's own message, so it never
// includes imported names. Each one works with the rule-based demo on any business.
const SUGGESTIONS = [
  "What if we hire someone at S$4,000 a month?",
  "What if we buy equipment for S$15,000 next month?",
  "Compare last month with the month before",
  "Which expenses grew the most?",
  "I need S$20,000 for 3 months. What are my options?",
];

function setDock(open) {
  app.classList.toggle("dock-closed", !open);
  if (open) {
    const box = dock.querySelector("textarea");
    if (box) box.focus();
  }
}

function setPending(prompt) {
  state.pending = prompt || null;
  renderDock();
}

/** Assistant text as plain text: "- " lines become a list, **x** becomes bold. Never HTML. */
function replyNodes(text) {
  const out = [];
  let list = null;
  const inline = (line) => line.split(/(\*\*[^*]+\*\*)/).map((part) => (part.startsWith("**") && part.endsWith("**") && part.length > 4 ? h("strong", {}, part.slice(2, -2)) : part));
  for (const line of String(text).split("\n")) {
    if (/^\s*[-*] /.test(line)) {
      if (!list) out.push((list = h("ul", {})));
      list.appendChild(h("li", {}, inline(line.replace(/^\s*[-*] /, ""))));
    } else {
      list = null;
      out.push(...inline(line), "\n");
    }
  }
  if (out[out.length - 1] === "\n") out.pop();
  return out;
}

// Long replies: the first line (the short answer) stays visible, the rest folds away. A reply
// that prepared an action is never folded, so what will happen is always on screen.
const FOLD_AFTER = 4;
function replyBody(m) {
  const lines = String(m.text).split("\n");
  const pending = (m.tools || []).some((t) => t.outcome === "pending");
  if (pending || lines.length <= FOLD_AFTER) return replyNodes(m.text);
  return [replyNodes(lines[0]), more(`Show details (${lines.length - 1} more lines)`, replyNodes(lines.slice(1).join("\n")))];
}

function messageNode(m) {
  if (m.who === "me") return h("div", { class: "msg me" }, m.text);
  if (m.who === "err") return h("div", { class: "msg err", role: "alert" }, m.text);
  if (m.who === "sys") return h("div", { class: "msg sys" }, m.text);
  return h("div", { class: "msg ai" }, replyBody(m), m.tools && m.tools.length ? h("div", { class: "tools" }, m.tools.map((t) => h("span", { class: `badge ${t.outcome === "ok" ? "neu" : "warn"}` }, t.tool))) : null);
}

function renderDock() {
  if (!state.me) return;
  const msgs = h(
    "div",
    { class: "msgs", "aria-live": "polite" },
    state.chat.length
      ? state.chat.map(messageNode)
      : h("div", { class: "chat-empty" }, h("div", { class: "hello" }, logo(40), h("b", {}, "Hi, I'm Fintellect")), h("p", {}, "The pages show your numbers. Ask me what they don't: what-ifs, comparisons, your own financing need, or to pay a bill or send a reminder (prepared first, and only run after you type the confirmation code). Try:"), SUGGESTIONS.map((q) => h("button", { class: "pill", type: "button", on: { click: () => send(q) } }, q))),
    state.busy ? h("div", { class: "msg ai busy" }, "Working…") : null,
  );
  const box = h("textarea", { rows: 1, maxlength: 2000, placeholder: state.pending ? "Type confirm and the code" : "Ask Fintellect…", "aria-label": "Message" });
  box.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      send(box.value);
    }
  });
  const left = state.me.messages_left;
  mount(
    dock,
    h(
      "div",
      { class: "dock-h" },
      h("span", { class: "chip-ic" }, icon("chat", 17)),
      h("div", { class: "t" }, h("b", {}, "Fintellect assistant"), h("small", {}, `${state.me.assistant_name}${left !== null && left !== undefined ? ` · ${left} messages left` : ""}`)),
      h("button", { class: "btn ghost sm", type: "button", "aria-label": "Close assistant", on: { click: () => setDock(false) } }, icon("close", 16)),
    ),
    msgs,
    state.pending
      ? h(
          "div",
          { class: "pending", role: "status" },
          h("div", { class: "eyebrow" }, "Waiting for your confirmation"),
          h("p", {}, state.pending),
          h("p", { class: "note" }, "To go ahead, type the confirm message with its code yourself. Anything else cancels it."),
        )
      : null,
    h(
      "form",
      { class: "ask", on: { submit: (ev) => { ev.preventDefault(); send(box.value); } } },
      h("div", { class: "inp" }, box),
      h("button", { class: "btn pri", type: "submit", disabled: state.busy, "aria-label": "Send" }, icon("send", 16)),
    ),
  );
  msgs.scrollTop = msgs.scrollHeight;
  if (!state.busy) box.focus({ preventScroll: true });
}

async function send(text) {
  const message = String(text || "").trim();
  if (!message || state.busy) return;
  state.chat.push({ who: "me", text: message });
  state.busy = true;
  renderDock();
  try {
    const reply = await api("/api/chat", { method: "POST", body: { message } });
    for (const n of reply.notices || []) state.chat.push({ who: "sys", text: n });
    if (reply.text) state.chat.push({ who: "ai", text: reply.text, tools: reply.trace });
    state.pending = reply.pending || null;
    state.me = await api("/api/session");
  } catch (e) {
    state.chat.push({ who: "err", text: e.message });
  }
  state.busy = false;
  renderDock();
  render(); // a confirmed payment or saved change shows up on the page straight away
}

// --- Start ------------------------------------------------------------------------------------
function start() {
  app.classList.remove("signed-out");
  renderSide();
  renderDock();
  render();
  if (!document.querySelector(".dock-open")) {
    app.appendChild(h("button", { class: "btn pri dock-open", type: "button", on: { click: () => setDock(true) } }, icon("chat", 16), "Assistant"));
  }
}

document.getElementById("scrim").addEventListener("click", () => app.classList.remove("open"));
window.addEventListener("hashchange", () => {
  renderSide();
  render();
});

(async () => {
  try {
    state.me = await api("/api/session");
  } catch {
    showSignIn();
    return;
  }
  start();
})();
