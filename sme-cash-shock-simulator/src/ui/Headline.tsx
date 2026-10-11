import type { Result, Scenario } from "../model/types";
import { headline, type Segment } from "./answer";
import { COLORS } from "./format";

function Line({ segs }: { segs: Segment[] }) {
  return (
    <>
      {segs.map((s, i) =>
        s.tone ? (
          <span key={i} style={{ color: s.tone === "bad" ? COLORS.shock : COLORS.profit }}>
            {s.text}
          </span>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </>
  );
}

/** Two lines of plain text that answer "do I survive, and what should I do". */
export default function Headline({ result, scenario }: { result: Result; scenario: Scenario }) {
  const h = headline(result, scenario);
  return (
    <section className="headline" aria-labelledby="headline-1" data-case={h.id}>
      <h1 id="headline-1" className="headline-1">
        <Line segs={h.line1} />
      </h1>
      <p className="headline-2">
        <Line segs={h.line2} />
      </p>
    </section>
  );
}
