"""Run an evaluation suite against the sandbox and print a scorecard.

python scripts/run_eval.py --suite redteam               # fooled model: structural defences
python scripts/run_eval.py --suite redteam --llm mock    # rule-based demo assistant
python scripts/run_eval.py --suite tasks                 # task suite on the rule-based mock
python scripts/run_eval.py --suite tasks --llm claude --effort low
python scripts/run_eval.py --suite redteam --case RT-IT-01 --show-replies

Red-team (tests/redteam/):
--llm fooled  plays a model that falls for every attack, so each case checks that policy, the
              confirmation step, the output guard and wrapping still keep the business safe.
--llm mock    sends the same user turns to the rule-based assistant (universal checks only).
--llm claude  the real model decides for itself; universal checks only.

Tasks (tests/tasks/): scripted conversations scored against ground_truth.json. The default
model is the mock (cases it can't do are skipped, with the reason); --llm claude runs them all.

--llm claude needs ANTHROPIC_API_KEY (agent/claude.py) and spends real money: the token use,
cost and time are printed. --effort overrides COPILOT_EFFORT for the run.
Exit code 1 if any case fails.
"""

from __future__ import annotations

import argparse
import sys
import time

from copilot.agent.mock_rules import RuleBasedLLM
from copilot.evals import evidence, redteam, tasks
from copilot.runtime import make_llm


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", choices=["redteam", "tasks"], default="redteam")
    parser.add_argument("--llm", choices=["fooled", "mock", "claude"])
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--case", action="append", help="run only these case ids")
    parser.add_argument("--show-replies", action="store_true")
    args = parser.parse_args()
    # Replies can hold characters a Windows console code page lacks (Claude writes "−").
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    llm = args.llm or ("fooled" if args.suite == "redteam" else "mock")
    if args.suite == "tasks" and llm == "fooled":
        parser.error("the fooled model is for the red-team suite only")
    if args.effort and llm != "claude":
        parser.error("--effort applies to --llm claude only")
    suite = redteam if args.suite == "redteam" else tasks
    cases = suite.load_cases()
    if args.case:
        cases = [c for c in cases if c.id in set(args.case)]
    made: list = []  # every model built, so the Claude run can total its token use

    def factory():
        made.append(RuleBasedLLM() if llm == "mock" else make_llm(llm, args.effort or ""))
        return made[-1]

    started = time.perf_counter()
    if args.suite == "redteam":
        results = redteam.run_suite(cases, None if llm == "fooled" else factory)
    else:
        results = tasks.run_suite(cases, factory)
    seconds = time.perf_counter() - started

    effort = f", effort {made[0].effort}" if llm == "claude" and made else ""
    title = "Red-team" if args.suite == "redteam" else "Task"
    print(f"{title} suite, model: {llm}{effort}, {len(results)} cases\n")
    print(suite.scorecard(results))
    if llm == "claude":
        print("\n" + usage_line(made))
        print(f"Time: {seconds:.0f}s in total, {seconds / max(len(results), 1):.1f}s per case")
    if args.show_replies:
        for r in results:
            print(f"\n{r.id} replies:")
            for text in r.replies:
                print(f"  > {text}")
    return 0 if all(r.passed for r in results) else 1


def usage_line(models: list) -> str:
    return "Claude usage: " + evidence.usage_line(evidence.usage_total([m.usage for m in models]))


if __name__ == "__main__":
    sys.exit(main())
