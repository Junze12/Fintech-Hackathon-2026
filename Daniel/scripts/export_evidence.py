"""Export execution evidence (deliverable #6): run the suites and write readable operation logs.

python scripts/export_evidence.py                     # offline: fooled red-team + mock tasks
python scripts/export_evidence.py --llm claude        # the submitted run (costs ~US$1.65)
python scripts/export_evidence.py --llm claude --case T-CF-01 --case RT-IT-01   # -> claude-partial/

Writes evidence/logs/<mode>/index.md, run.json and one Markdown file per case
(copilot/evals/evidence.py has the details). fooled and claude are committed; mock is
regenerated on demand. --llm claude needs ANTHROPIC_API_KEY and spends real money.
Exit code 1 if any case fails (the files are still written).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from copilot.evals.evidence import export, folder_for, usage_line
from copilot.runtime import ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--llm", choices=["offline", "claude"], default="offline")
    parser.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--case", action="append", help="export only these case ids")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence" / "logs")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    if args.effort and args.llm != "claude":
        parser.error("--effort applies to --llm claude only")

    modes = ["claude"] if args.llm == "claude" else ["fooled", "mock"]
    ok = True
    for mode in modes:
        run = export(mode, args.out, case_ids=args.case, effort=args.effort or "")  # type: ignore[arg-type]
        ok &= run.passed
        print(f"== {mode}: {run.model}{f', effort {run.effort}' if run.effort else ''}\n")
        for card in run.scorecards.values():
            print(card + "\n")
        if run.usage:
            print(f"Claude usage: {usage_line(run.usage)}\n")
        print(f"Written to {folder_for(args.out, mode, args.case)}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
