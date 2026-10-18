// Display formatting only. The API sends money as decimal strings ("-13025.81"); these helpers
// turn them into text without doing any arithmetic on the amounts (rounding happens only where
// a value has more decimals than it is shown with). Along with charts.js this is the only
// module allowed to convert strings to numbers.

const MINUS = "−";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function groups(intPart) {
  return intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function parts(str, dp) {
  let text = String(str).trim();
  const neg = text.startsWith("-");
  if (neg || text.startsWith("+")) text = text.slice(1);
  let [whole, frac = ""] = text.split(".");
  if (frac.length > dp) {
    const fixed = Number(text).toFixed(dp); // display rounding only
    [whole, frac = ""] = fixed.split(".");
  }
  frac = frac.padEnd(dp, "0");
  const zero = /^0*$/.test(whole + frac);
  return { neg: neg && !zero, whole: groups(whole || "0"), frac };
}

export function isMissing(v) {
  return v === null || v === undefined || v === "";
}

export function isNeg(v) {
  return !isMissing(v) && parts(v, 2).neg;
}

/** True for "0", "0.00", "-0.00". */
export function isZero(v) {
  return !isMissing(v) && /^[-+]?0*\.?0*$/.test(String(v).trim());
}

/** "-13025.81" -> "−S$13,025.81"; dp=0 for whole dollars. */
export function money(v, dp = 2) {
  if (isMissing(v)) return "—";
  const p = parts(v, dp);
  return `${p.neg ? MINUS : ""}S$${p.whole}${dp ? "." + p.frac : ""}`;
}

/** Signed money for changes: "+S$1,200.00" / "−S$85,000.00". */
export function signed(v) {
  if (isMissing(v)) return "—";
  const p = parts(v, 2);
  const zero = /^[0,]*$/.test(p.whole) && /^0*$/.test(p.frac);
  return (p.neg || zero ? "" : "+") + money(v);
}

/** A value already in percent ("96.10") -> "96.10%" as given. */
export function pct(v) {
  return isMissing(v) ? "—" : `${String(v).replace("-", MINUS)}%`;
}

/** A fraction ("0.4426") -> "44.3%". */
export function share(v, dp = 1) {
  if (isMissing(v)) return "—";
  const p = parts((Number(v) * 100).toFixed(dp), dp);
  return `${p.neg ? MINUS : ""}${p.whole}${dp ? "." + p.frac : ""}%`;
}

/** Plain number with thousands separators, as given ("28.8" -> "28.8"). */
export function num(v) {
  if (isMissing(v)) return "—";
  const text = String(v);
  const neg = text.startsWith("-");
  const [whole, frac] = (neg ? text.slice(1) : text).split(".");
  return `${neg ? MINUS : ""}${groups(whole)}${frac !== undefined ? "." + frac : ""}`;
}

/** "2026-11-05" -> "5 Nov 2026" */
export function date(v) {
  if (isMissing(v)) return "—";
  const [y, m, d] = String(v).split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`;
}

/** "2026-11-05" -> "5 Nov" */
export function day(v) {
  if (isMissing(v)) return "—";
  const [, m, d] = String(v).split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1]}`;
}

/** "2026-10" -> "Oct 2026" */
export function month(v) {
  if (isMissing(v)) return "—";
  const [y, m] = String(v).split("-");
  return `${MONTHS[Number(m) - 1]} ${y}`;
}

/** Short axis label for money: 150000 -> "150k". */
export function axisMoney(n) {
  const a = Math.abs(n);
  const sign = n < 0 ? MINUS : "";
  if (a >= 1e6) return `${sign}${(a / 1e6).toFixed(a % 1e6 ? 1 : 0)}M`;
  if (a >= 1e3) return `${sign}${(a / 1e3).toFixed(a % 1e3 ? 1 : 0)}k`;
  return `${sign}${a.toFixed(0)}`;
}

/** "snake_case_key" -> "Snake case key" (for labels the API gives only as keys). */
export function label(key) {
  const text = String(key).replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Sentence case for short labels from API keys: "critical" -> "Critical", "below target" -> "Below target". */
export function cap(text) {
  const t = String(text ?? "");
  return t.charAt(0).toUpperCase() + t.slice(1);
}
