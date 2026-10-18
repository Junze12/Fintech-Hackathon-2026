// Glossary: every term behind the (i) icons, grouped by page, with a filter box. Static text
// from glossary.js only; no API calls.
import { h, mount } from "../dom.js";
import { GROUPS, TERMS } from "../glossary.js";
import { card } from "../ui.js";

let filter = "";

function matches(t) {
  const q = filter.trim().toLowerCase();
  return !q || t.term.toLowerCase().includes(q) || t.text.toLowerCase().includes(q);
}

function list() {
  const all = Object.values(TERMS).filter(matches);
  if (!all.length) return h("p", { class: "note" }, "No term matches that search.");
  return GROUPS.map((g) => {
    const terms = all.filter((t) => t.group === g).sort((a, b) => a.term.localeCompare(b.term, "en"));
    if (!terms.length) return null;
    return card(g, null, h("dl", { class: "gloss" }, terms.map((t) => [h("dt", {}, t.term), h("dd", {}, t.text)])));
  });
}

export default {
  key: "glossary",
  nav: "Glossary",
  icon: "book",
  title: "Glossary",
  subtitle: "What the terms on this dashboard mean. The (i) icons next to labels show the same text.",
  endpoints: [],
  async render(root) {
    const out = h("div", { class: "stack" }, list());
    const onInput = (ev) => {
      filter = ev.target.value;
      mount(out, list());
    };
    const input = h("input", { type: "search", class: "gsearch", placeholder: "Search terms", "aria-label": "Search terms", value: filter, autocomplete: "off", on: { input: onInput } });
    mount(root, input, out);
  },
};
