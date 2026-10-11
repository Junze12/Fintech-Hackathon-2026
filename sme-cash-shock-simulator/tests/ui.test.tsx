import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Result, Scenario } from "../src/model/types";
import { analyse } from "../src/sim/analyse";
import CashCompare from "../src/ui/CashCompare";
import Comparison from "../src/ui/Comparison";
import Controls from "../src/ui/Controls";
import Details from "../src/ui/Details";
import GapBridge from "../src/ui/GapBridge";
import Headline from "../src/ui/Headline";
import OptionsTable from "../src/ui/OptionsTable";
import PaymentCard from "../src/ui/PaymentCard";
import Timeline from "../src/ui/Timeline";
import { VerdictSummary, SurvivalCurve } from "../src/ui/VerdictBar";
import { gapBridge, headline, modalFailDay, pathOf, recommended, segmentsText, strategyOf } from "../src/ui/answer";
import { fmtMoney, fmtPct } from "../src/ui/format";
import { planSentence } from "../src/model/plan";
import { loadNearEdge, loadSample, quick, withFields } from "./helpers";

const run = (s: Scenario): Result => analyse(s, { deterministic: false, scenarioName: "t" });
const text = (h: ReturnType<typeof headline>) => [segmentsText(h.line1), segmentsText(h.line2)];

describe("formatting and plan sentence", () => {
  it("money and percent formats", () => {
    expect(fmtMoney(1234.5)).toBe("S$1,235");
    expect(fmtMoney(-1234)).toBe("-S$1,234");
    expect(fmtMoney(1234.5, 2)).toBe("S$1,234.50");
    expect(fmtMoney(-0.001)).toBe("S$0");
    expect(fmtPct(0.9547)).toBe("95.5%");
  });
  it("plan sentence matches the spec's example", () => {
    expect(
      planSentence(loadSample(), { D1: ["late_fee"], D2: ["letter"], D3: [], D4: ["pay_due"] }),
    ).toBe(
      "Day 10: Charge late fee (Firm A). Day 10: Letter of demand (Firm B). Day 35: No action. Day 45: Pay on due date (Inventory).",
    );
  });
});

describe("A6.1 headline cases", () => {
  it("case 1: doing nothing covers a S$20,000 shock", () => {
    const s = quick(withFields(loadNearEdge(), (c) => (c.shocks[0].amount = 20000)));
    const r = run(s);
    const h = headline(r, s);
    expect(h.id).toBe("1");
    const s0 = strategyOf(r, "S0").survivalProb;
    expect(text(h)).toEqual([
      "You can cover the S$20,000 on day 25 without doing anything.",
      `${Math.round(s0 * 100)}% of simulated runs make it.`,
    ]);
    expect(h.line1[1]).toMatchObject({ text: "S$20,000", tone: "good" });
  });

  it("case 2: S$30,000 leaves a gap that the best move closes", () => {
    const s = quick(loadNearEdge());
    const r = run(s);
    const h = headline(r, s);
    const R = recommended(r);
    expect(h.id).toBe("2");
    expect(R.survivalProb).toBeGreaterThanOrEqual(0.95);
    expect(text(h)).toEqual([
      `Without action you'll be ${fmtMoney(r.defaultGap.gapAtShock)} short on day 25.`,
      `Best move: ${R.name}. ${R.cost < 0 ? `Gains ${fmtMoney(-R.cost)}` : `Costs ${fmtMoney(R.cost)}`}, and ${Math.round(R.survivalProb * 100)}% of runs survive.`,
    ]);
    expect(h.line1[1].tone).toBe("bad");
  });

  it("case 3: S$45,000 cannot be covered by any plan", () => {
    const s = quick(withFields(loadNearEdge(), (c) => (c.shocks[0].amount = 45000)));
    const r = run(s);
    const h = headline(r, s);
    const R = recommended(r);
    expect(h.id).toBe("3");
    expect(R.gapAtShock).toBeGreaterThan(0);
    const extra = r.threshold.extraBufferForChosenShock;
    expect(text(h)).toEqual([
      `Even the best plan leaves you ${fmtMoney(R.gapAtShock)} short on day 25.`,
      `You need ${extra === null ? `more than ${fmtMoney(40000)}` : `about ${fmtMoney(extra)}`} more cash or credit before day 25.`,
    ]);
    expect(h.line1[1].tone).toBe("bad");
  });

  it("case 4: the shock is covered but a later bill breaks the business", () => {
    const s = quick(
      withFields(loadNearEdge(), (c) => {
        c.shocks[0].amount = 10000;
        c.payables.push({ id: "AP-BIG", label: "Big bill", amount: 30000, dueDay: 50, affectsProfit: true, earlyPayDiscount: null });
      }),
    );
    const r = run(s);
    const h = headline(r, s);
    const R = recommended(r);
    expect(h.id).toBe("4");
    expect(R.survivalProb).toBeLessThan(0.95);
    expect(R.gapAtShock).toBe(0);
    const modal = modalFailDay(pathOf(r, R.pathId).metrics.failDayHistogram);
    expect(modal).toBe(50);
    expect(text(h)).toEqual([
      "You can cover day 25, but the business still runs short later.",
      "Most failures happen on day 50.",
    ]);
  });

  it("case 2 variants: runs short later (no gap) and a negative cost reads 'Gains'", () => {
    const s = loadNearEdge();
    const fake = (gap0: number, cost: number) =>
      ({
        strategies: [
          { id: "S0", name: "Do nothing", description: "", pathId: "a", survivalProb: 0.9, cost: 0, gapAtShock: gap0, churnRisk: [], isRecommended: false },
          { id: "S1", name: "Plan B", description: "", pathId: "b", survivalProb: 0.99, cost, gapAtShock: 0, churnRisk: [], isRecommended: true },
        ],
        defaultGap: { gapAtShock: gap0, extraBufferForChosenShock: 0 },
        threshold: { extraBufferForChosenShock: 0 },
        paths: [],
      }) as unknown as Result;
    expect(text(headline(fake(0, 50), s))[0]).toBe("Without action the business runs short after day 25.");
    expect(headline(fake(0, 50), s).id).toBe("2b");
    expect(text(headline(fake(2000, -120), s))[1]).toBe("Best move: Plan B. Gains S$120, and 99% of runs survive.");
  });

  it("modal failure day: most failures, ties to the earliest day", () => {
    expect(modalFailDay({ "45": 3, "60": 7, "30": 7 })).toBe(30);
    expect(modalFailDay({})).toBeNull();
  });
});

describe("A6.2 gap bridge", () => {
  for (const [name, load] of [["shock-near-edge", loadNearEdge], ["hand-drawn", loadSample]] as const) {
    it(`bars 1-6 add up to bar 7 for every strategy in ${name}`, () => {
      const s = quick(load());
      const r = run(s);
      for (const st of r.strategies) {
        const b = gapBridge(r, s, st.id);
        expect(b.bars.length).toBe(7);
        expect(Math.abs(b.reached - b.worst)).toBeLessThan(1);
        expect(b.adds).toBe(true);
        expect(b.bars[4].hidden).toBe(st.id === "S0");
        expect(b.bars[0].value).toBe(s.business.cash0);
        expect(b.bars[3].value).toBe(s.creditLines.reduce((a, l) => a + l.limit, 0));
      }
    });
  }
});

describe("panels render from a real Result", () => {
  const s = quick(loadNearEdge());
  const result = run(s);
  const R = recommended(result);

  it("headline, bridge, options table, cash chart and payment card render", () => {
    expect(renderToStaticMarkup(<Headline result={result} scenario={s} />)).toContain("short on day 25");
    const bridge = renderToStaticMarkup(<GapBridge result={result} scenario={s} strategyId={R.id} />);
    expect(bridge).toContain("Cash you can reach on day 25");
    expect(bridge).toContain("Worst likely position = the level you stay above in 95% of simulated runs.");
    const table = renderToStaticMarkup(<OptionsTable result={result} scenario={s} selectedId={R.id} onSelect={() => {}} />);
    expect(table).toContain("Recommended");
    expect(table).toContain("Still short on day 25");
    expect(table).toContain("Covered");
    expect(table).toContain("chance of losing Firm A");
    expect(table.match(/<tr/g)!.length).toBe(result.strategies.length + 1);
    expect(renderToStaticMarkup(<CashCompare result={result} scenario={s} strategyId="S2" />)).toContain("Pressure Firm A vs doing nothing");
    const pay = renderToStaticMarkup(<PaymentCard result={result} scenario={s} strategyId="S2" />);
    expect(pay).toContain("How your customers pay");
    expect(pay).toContain("Firm A");
  });

  it("details are collapsed by default; their parts render on their own", () => {
    const html = renderToStaticMarkup(
      <Details result={result} scenario={s} strategyId="S2" pinnedPathId={null} onPin={() => {}} />,
    );
    expect(html).toContain("Show details: full financials, decision tree, assumptions");
    expect(html).not.toContain("Decision tree");
    expect(renderToStaticMarkup(<VerdictSummary result={result} scenario={s} />)).toContain("Largest survivable shock");
    expect(renderToStaticMarkup(<SurvivalCurve result={result} scenario={s} />)).toContain("Survival curve");
    const cmp = renderToStaticMarkup(<Comparison result={result} strategyId="S2" />);
    expect(cmp).toContain("Financing fees");
    expect(cmp).toContain("Peak credit drawn");
    for (const pin of [null, result.paths[3].id]) {
      expect(renderToStaticMarkup(<Timeline result={result} scenario={s} pathId={result.bestPathId} pinnedPathId={pin} />)).toContain("Cash timeline with events");
    }
  });

  it("Controls render the run button, picker, add-row buttons and objective editor", () => {
    const html = renderToStaticMarkup(
      <Controls scenario={s} onChange={() => {}} deterministic={false} onDeterministic={() => {}} scenarioName="x"
        choices={[{ key: "a", label: "A" }]} selectedKey="a" onPick={() => {}} onLoad={() => {}} onError={() => {}}
        onRun={() => {}} running={false} stale={true} validationError={null} />,
    );
    for (const t of ["Run simulator", "Inputs changed", "Add customer", "Add supplier bill", "Add order line",
      "Load scenario JSON", "Download scenario JSON", "Deterministic", "Starting cash", "What can I write?"]) {
      expect(html).toContain(t);
    }
  });
});
