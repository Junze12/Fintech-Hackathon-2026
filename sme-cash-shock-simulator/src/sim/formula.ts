// A small, safe expression language for the ranking value (no eval).
//
//   expr    := term (("+" | "-") term)*
//   term    := unary (("*" | "/") unary)*
//   unary   := ("-" | "+") unary | primary
//   primary := number | variable | function "(" expr ("," expr)* ")" | "(" expr ")"
//
// Variables are per-path means over the simulated runs. Functions: min, max, abs.

export const FORMULA_VARIABLES: { name: string; description: string }[] = [
  { name: "economicProfit", description: "Profit minus the margin lost after the horizon (churn cost). The default ranking value." },
  { name: "profit", description: "Gross profit minus discounts, costs, interest and financing fees, plus late fees and supplier discounts." },
  { name: "revenue", description: "Invoiced sales inside the horizon." },
  { name: "grossProfit", description: "Revenue minus cost of goods." },
  { name: "discountsGiven", description: "Discounts given to customers." },
  { name: "lateFeeIncome", description: "Late fees collected." },
  { name: "supplierDiscounts", description: "Discounts earned by paying suppliers early." },
  { name: "collectionCosts", description: "Cash spent on collection actions such as letters of demand." },
  { name: "operatingExpense", description: "Bills and recurring costs that count as expenses." },
  { name: "interestExpense", description: "Interest on credit lines." },
  { name: "financingFees", description: "Fees paid for invoice financing." },
  { name: "shockExpense", description: "The shock, if the scenario counts it as an expense (otherwise 0)." },
  { name: "churnCost", description: "Margin lost after the horizon from customers who left." },
  { name: "endNetCash", description: "Cash minus credit drawn, accrued interest and financing outstanding on the last day." },
  { name: "endReceivables", description: "Money still owed to you on the last day." },
  { name: "endPayables", description: "Bills still unpaid on the last day." },
  { name: "survivalProb", description: "Share of runs that survive (0 to 1)." },
  { name: "daysSurvived", description: "Average days survived: the failure day for a failed run, the horizon for a survivor." },
];

export const FORMULA_FUNCTIONS = ["min", "max", "abs"] as const;
export const DEFAULT_FORMULA = "economicProfit";
const NAMES = new Set(FORMULA_VARIABLES.map((v) => v.name));

export type Vars = Record<string, number>;
export type ParseResult =
  | { ok: true; evaluate: (vars: Vars) => number; used: string[] }
  | { ok: false; message: string };

type Token =
  | { t: "num"; v: number; pos: number }
  | { t: "id"; v: string; pos: number }
  | { t: "op"; v: string; pos: number };

function tokenize(src: string): Token[] | string {
  const out: Token[] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (/\s/.test(c)) {
      i++;
    } else if (/[0-9.]/.test(c)) {
      const m = /^(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?/.exec(src.slice(i));
      if (!m) return `Cannot read the number at position ${i + 1}`;
      out.push({ t: "num", v: Number(m[0]), pos: i });
      i += m[0].length;
    } else if (/[A-Za-z_]/.test(c)) {
      const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(src.slice(i))!;
      out.push({ t: "id", v: m[0], pos: i });
      i += m[0].length;
    } else if ("+-*/(),".includes(c)) {
      out.push({ t: "op", v: c, pos: i });
      i++;
    } else {
      return `Unexpected character "${c}" at position ${i + 1}`;
    }
  }
  return out;
}

type Node = (vars: Vars) => number;

/** Parse a formula. Never throws; returns a message naming the offending term. */
export function parseFormula(src: string): ParseResult {
  const toks = tokenize(src);
  if (typeof toks === "string") return { ok: false, message: toks };
  if (toks.length === 0) return { ok: false, message: "The formula is empty" };
  let p = 0;
  const used = new Set<string>();

  class Fail extends Error {}
  const fail = (m: string): never => {
    throw new Fail(m);
  };
  const peek = () => toks[p];
  const isOp = (v: string) => peek()?.t === "op" && (peek() as { v: string }).v === v;

  const expr = (): Node => {
    let left = term();
    while (isOp("+") || isOp("-")) {
      const op = (toks[p++] as { v: string }).v;
      const right = term();
      const l = left;
      left = op === "+" ? (v) => l(v) + right(v) : (v) => l(v) - right(v);
    }
    return left;
  };
  const term = (): Node => {
    let left = unary();
    while (isOp("*") || isOp("/")) {
      const op = (toks[p++] as { v: string }).v;
      const right = unary();
      const l = left;
      left = op === "*" ? (v) => l(v) * right(v) : (v) => l(v) / right(v);
    }
    return left;
  };
  const unary = (): Node => {
    if (isOp("-")) {
      p++;
      const x = unary();
      return (v) => -x(v);
    }
    if (isOp("+")) {
      p++;
      return unary();
    }
    return primary();
  };
  const primary = (): Node => {
    const tok = toks[p];
    if (!tok) return fail("The formula ends too early; a value is missing at the end");
    if (tok.t === "num") {
      p++;
      return () => tok.v;
    }
    if (tok.t === "id") {
      p++;
      if (isOp("(")) {
        if (!(FORMULA_FUNCTIONS as readonly string[]).includes(tok.v))
          return fail(`Unknown function "${tok.v}". Use min, max or abs`);
        p++;
        const args: Node[] = [expr()];
        while (isOp(",")) {
          p++;
          args.push(expr());
        }
        if (!isOp(")")) return fail(`Missing ")" after the arguments of ${tok.v}`);
        p++;
        if (tok.v === "abs") {
          if (args.length !== 1) return fail("abs takes exactly one value");
          const a = args[0];
          return (v) => Math.abs(a(v));
        }
        if (args.length < 2) return fail(`${tok.v} needs at least two values`);
        return tok.v === "min"
          ? (v) => Math.min(...args.map((a) => a(v)))
          : (v) => Math.max(...args.map((a) => a(v)));
      }
      if (!NAMES.has(tok.v))
        return fail(`Unknown variable "${tok.v}". See the list of variables you can use`);
      used.add(tok.v);
      const name = tok.v;
      return (v) => v[name];
    }
    if (tok.v === "(") {
      p++;
      const e = expr();
      if (!isOp(")")) return fail('Missing ")" to close the bracket');
      p++;
      return e;
    }
    return fail(`Unexpected "${tok.v}" at position ${tok.pos + 1}`);
  };

  try {
    const root = expr();
    if (p < toks.length) {
      const t = toks[p];
      return { ok: false, message: `Unexpected "${t.v}" at position ${t.pos + 1}` };
    }
    // A value that cannot be calculated (for example dividing by zero) ranks last.
    const evaluate = (vars: Vars) => {
      const r = root(vars);
      return Number.isFinite(r) ? r : -1e18;
    };
    return { ok: true, evaluate, used: [...used] };
  } catch (e) {
    if (e instanceof Fail) return { ok: false, message: e.message };
    throw e;
  }
}

/** The ranking value function for a scenario: undefined when the default (economicProfit) applies. */
export function valueFunction(formula: string | undefined): ((vars: Vars) => number) | undefined {
  if (formula === undefined || formula.trim() === DEFAULT_FORMULA) return undefined;
  const r = parseFormula(formula);
  if (!r.ok) throw new Error(`objective.valueFormula: ${r.message}`);
  return r.evaluate;
}
