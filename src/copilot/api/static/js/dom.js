// The only way this page builds DOM (known risk R38). Every string becomes a text node, never
// HTML, so an imported name such as "<img src=x onerror=...>" shows as those characters.
// Attributes go through setAttribute with an allowlist: no event handlers, no style strings,
// no src, and href only for in-page "#route" links, the two /api/export downloads and the
// upload templates (/api/upload/template/<file>.csv).
// Event handlers are passed as functions.

const SVG_NS = "http://www.w3.org/2000/svg";

const HTML_ATTRS = new Set([
  "class", "id", "role", "type", "name", "value", "for", "title", "placeholder", "min", "max",
  "step", "disabled", "checked", "selected", "colspan", "hidden", "tabindex", "autocomplete",
  "maxlength", "inputmode", "required", "rows", "lang", "open", "download", "multiple", "accept",
]);
const SVG_ATTRS = new Set([
  "class", "role", "viewBox", "width", "height", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy",
  "r", "rx", "d", "points", "text-anchor", "dominant-baseline", "preserveAspectRatio",
  "stroke-width", "fill", "stroke",
]);

function allowed(name, svg) {
  if (name.startsWith("aria-") || name.startsWith("data-")) return true;
  return (svg ? SVG_ATTRS : HTML_ATTRS).has(name);
}

function apply(el, attrs, svg) {
  for (const [name, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (name === "on") {
      for (const [ev, fn] of Object.entries(value)) el.addEventListener(ev, fn);
    } else if (name === "style") {
      // CSSOM only (allowed by the page's Content-Security-Policy); values come from charts.js
      for (const [prop, v] of Object.entries(value)) el.style.setProperty(prop, String(v));
    } else if (name === "href") {
      // In-page routes, the two same-origin Excel downloads (query values are enum words) and
      // the upload templates (file names come from the server's allowlist)
      const ok =
        /^#[a-z0-9-]*$/.test(String(value)) ||
        /^\/api\/export\/(statements|forecast)\.xlsx(\?[a-z0-9_=&-]*)?$/.test(String(value)) ||
        /^\/api\/upload\/template\/[a-z_]+\.csv$/.test(String(value));
      if (!ok) throw new Error("Only in-page links and the dashboard's downloads are allowed");
      el.setAttribute("href", String(value));
    } else if (allowed(name, svg)) {
      el.setAttribute(name, value === true ? "" : String(value));
    } else {
      throw new Error(`Attribute not allowed: ${name}`);
    }
  }
}

function append(el, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.appendChild(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

/** h("div", {class: "card"}, "text", child, [more]) -> HTMLElement */
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  apply(el, attrs, false);
  return append(el, kids);
}

/** s("path", {d: "..."}) -> SVGElement */
export function s(tag, attrs, ...kids) {
  const el = document.createElementNS(SVG_NS, tag);
  apply(el, attrs, true);
  return append(el, kids);
}

/** Replace everything inside el with kids. */
export function mount(el, ...kids) {
  el.replaceChildren();
  return append(el, kids);
}

const ICONS = {
  chart: ["M4 19V5", "M4 19h16", "M8 15l4-5 3 3 5-7"],
  home: ["M3 11l9-7 9 7", "M5 10v10h14V10"],
  plan: ["M12 3v18", "M5 8h14", "M7 14h10"],
  outlook: ["M3 17l6-6 4 4 8-8", "M15 7h6v6"],
  doc: ["M7 3h8l4 4v14H7z", "M15 3v4h4", "M10 12h6", "M10 16h6"],
  check: ["M9 12l2 2 4-4", "M12 3a9 9 0 1 0 0.01 0"],
  chat: ["M4 5h16v11H9l-5 4z"],
  clock: ["M12 7v5l3 2", "M12 3a9 9 0 1 0 0.01 0"],
  menu: ["M4 7h16", "M4 12h16", "M4 17h16"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  out: ["M15 12H4", "M8 8l-4 4 4 4", "M12 4h7v16h-7"],
  sun: ["M12 8a4 4 0 1 0 0.01 0", "M12 2v2", "M12 20v2", "M4 12H2", "M22 12h-2"],
  cash: ["M3 7h18v10H3z", "M12 10a2 2 0 1 0 0.01 0"],
  alert: ["M12 4l9 16H3z", "M12 10v4", "M12 17v.5"],
  people: ["M9 5a3.2 3.2 0 1 1 0 6.4a3.2 3.2 0 0 1 0-6.4", "M3 20c0-3.3 2.7-5.6 6-5.6s6 2.3 6 5.6", "M16 6a2.6 2.6 0 1 1 0 5.2", "M17.5 14.7c2.1.6 3.5 2.5 3.5 5.3"],
  send: ["M4 12l16-8-6 16-2-7z"],
  down: ["M12 4v11", "M7 10l5 5 5-5", "M5 20h14"],
  book: ["M5 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H5z", "M19 4h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6z"],
  overdue: ["M13 21H6V3h8l4 4v4", "M14 3v4h4", "M9 9h4", "M9 13h3", "M17 13a4 4 0 1 0 0.01 0", "M17 15v2l1.5 1"],
};

/** A small line icon from the fixed set above. */
export function icon(name, size = 18) {
  return s(
    "svg",
    { viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor", "stroke-width": 1.8, "aria-hidden": "true" },
    (ICONS[name] || []).map((d) => s("path", { d })),
  );
}
