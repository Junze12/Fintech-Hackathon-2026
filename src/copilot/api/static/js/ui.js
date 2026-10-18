// Small shared building blocks for the pages (cards, KPI tiles, tables, forms).
import { h, icon } from "./dom.js";
import { cap, isNeg, money } from "./fmt.js";
import { TERMS } from "./glossary.js";

export function card(title, sub, ...kids) {
  return h("section", { class: "card" }, h("div", { class: "card-h" }, h("div", { class: "t" }, h("h2", {}, title), sub ? h("p", {}, sub) : null)), kids);
}

// Section colours: a "tone-<name>" class on a card adds a small coloured icon to its title,
// so cash, forecast, risk and financing sections can be told apart at a glance.
const TONES = {
  cash: ["cash", "g"], people: ["people", "g"], plan: ["plan", "g"],
  forecast: ["outlook", "b"], doc: ["doc", "b"],
  risk: ["alert", "a"], check: ["check", "a"],
  fin: ["cash", "v"], value: ["chart", "v"],
};

export function cardWith(cls, title, sub, right, ...kids) {
  const tone = TONES[((cls || "").match(/\btone-(\w+)/) || [])[1]];
  const chip = tone ? h("span", { class: `sec-ic t${tone[1]}` }, icon(tone[0], 16)) : null;
  return h(
    "section",
    { class: `card ${cls || ""}` },
    h("div", { class: "card-h" }, chip, h("div", { class: "t" }, h("h2", {}, title), sub ? h("p", {}, sub) : null), right),
    kids,
  );
}

/** Long text on `lines` lines (1 or 2) with a More / Less button, shown only if it overflows. */
export function clamp(text, lines = 2, cls = "") {
  const body = h("span", { class: `clamp-t l${lines} ${cls}` }, text);
  const btn = h("button", { class: "clamp-b", type: "button", hidden: true, on: { click: () => (btn.textContent = wrap.classList.toggle("open") ? "Less" : "More") } }, "More");
  const wrap = h("span", { class: "clamp" }, body, btn);
  requestAnimationFrame(() => (btn.hidden = body.scrollHeight <= body.clientHeight + 1));
  return wrap;
}

export function kpi(ic, label, value, foot, tone = "") {
  return h(
    "div",
    { class: "card kpi" },
    h("div", { class: "kpi-h" }, h("span", { class: `chip-ic ${tone}` }, icon(ic, 17)), h("span", { class: "l" }, label)),
    h("div", { class: `kpi-v ${tone === "neg" ? "neg" : ""}` }, value),
    foot ? h("div", { class: "kpi-f" }, foot) : null,
  );
}

export function badge(tone, text) {
  return h("span", { class: `badge ${tone}` }, cap(text));
}

export const SEVERITY_TONE = { critical: "neg", high: "neg", warning: "warn", medium: "warn", info: "info", low: "neu" };

/** A message box for a panel the user can't see or that failed (the gateway's own reason). */
export function panelMessage(text) {
  return h("div", { class: "pmsg", role: "status" }, text);
}

/** Money cell, red when negative. */
export function moneyCell(v) {
  return h("td", { class: `n ${isNeg(v) ? "neg" : ""}` }, money(v));
}

export function table(headers, rows, cls = "") {
  return h(
    "div",
    { class: "tw" },
    h(
      "table",
      { class: cls },
      h("thead", {}, h("tr", {}, headers.map((x) => (typeof x === "string" || x instanceof Node ? h("th", {}, x) : h("th", { class: x.cls || "" }, x.text))))),
      h("tbody", {}, rows),
    ),
  );
}

export function sumrow(label, value, cls = "") {
  return h("div", { class: `sumrow ${cls}` }, h("span", {}, label), h("b", {}, value));
}

/** Segmented buttons; onPick(value) is called on click. */
export function seg(options, current, onPick, labelText) {
  return h(
    "div",
    { class: "seg", role: "group", "aria-label": labelText || "Choose" },
    options.map(([value, text, dot]) =>
      h(
        "button",
        { type: "button", "aria-pressed": String(value === current), on: { click: () => onPick(value) } },
        dot ? h("i", { class: `dot ${dot}` }) : null,
        text,
      ),
    ),
  );
}

/** A labelled text input inside the form grid. */
export function field(id, labelText, value, { pre, suf, hint, type = "text", inputmode } = {}) {
  const input = h("input", { id, name: id, type, value: value ?? "", inputmode, autocomplete: "off" });
  return {
    input,
    el: h("div", { class: "field" }, h("label", { for: id }, labelText), h("div", { class: "inp" }, pre ? h("span", { class: "pre" }, pre) : null, input, suf ? h("span", { class: "suf" }, suf) : null), hint ? h("small", {}, hint) : null),
  };
}

export function warnings(list) {
  if (!list || !list.length) return null;
  return h("div", { class: "notes" }, list.map((w) => h("p", { class: "note" }, w)));
}

export function loading(text = "Loading…") {
  return h("p", { class: "loading", role: "status" }, text);
}

/** A collapsed section; isOpen/onToggle keep it open across re-renders when needed. */
export function more(title, kids, isOpen = false, onToggle = null) {
  const d = h("details", { class: "more", open: isOpen }, h("summary", {}, title), h("div", { class: "more-body" }, kids));
  if (onToggle) d.addEventListener("toggle", () => onToggle(d.open));
  return d;
}

// --- (i) icons: one shared tooltip, placed next to the icon (CSS clamps it to the screen) ---
let tip = null;
function tooltip() {
  if (!tip) {
    tip = h("div", { class: "tip", id: "term-tip", role: "tooltip", hidden: true });
    document.body.appendChild(tip);
  }
  return tip;
}
function showTip(btn, t) {
  const el = tooltip();
  el.replaceChildren(h("b", {}, t.term), h("span", {}, t.text));
  const r = btn.getBoundingClientRect();
  el.style.setProperty("--x", `${r.left}px`);
  el.style.setProperty("--y", `${r.bottom}px`);
  el.hidden = false;
}
function hideTip() {
  if (tip) tip.hidden = true;
}
document.addEventListener("keydown", (ev) => ev.key === "Escape" && hideTip());
document.addEventListener("click", hideTip);
window.addEventListener("hashchange", hideTip);
window.addEventListener("scroll", hideTip, true);

/** An (i) button explaining a glossary term on hover, focus or tap. */
export function info(key) {
  const t = TERMS[key];
  if (!t) throw new Error(`Unknown glossary term: ${key}`);
  return h("button", {
    class: "term-i",
    type: "button",
    "aria-label": `What is ${t.term}?`,
    "aria-describedby": "term-tip",
    on: {
      mouseenter: (ev) => showTip(ev.currentTarget, t),
      mouseleave: hideTip,
      focus: (ev) => showTip(ev.currentTarget, t),
      blur: hideTip,
      click: (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        showTip(ev.currentTarget, t);
      },
    },
  }, "i");
}

/** A label followed by its (i) icon. */
export function term(text, key) {
  return h("span", { class: "term" }, text, info(key));
}

/** A link that downloads one of the dashboard's Excel files (dom.js only allows these). */
export function download(path, query, text) {
  const q = new URLSearchParams(Object.entries(query || {}).filter(([, v]) => v)).toString();
  return h("a", { class: "btn ghost dl", href: q ? `${path}?${q}` : path, download: "" }, icon("down", 15), text);
}
