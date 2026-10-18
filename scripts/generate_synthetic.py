"""Generate the synthetic businesses into data/synthetic/<scenario>/.

python scripts/generate_synthetic.py                 # all scenarios, seed 42
python scripts/generate_synthetic.py --seed 7 --out /tmp/synth --scenario cash_crunch
"""

from __future__ import annotations

import argparse
from pathlib import Path

from copilot.synthetic import (
    INJECTION_KEY,
    MESSY_KEY,
    SCENARIOS,
    generate,
    messy_books_variant,
    prompt_injection_variant,
)

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = [INJECTION_KEY, MESSY_KEY]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "synthetic")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS) + VARIANTS, action="append")
    args = parser.parse_args()

    for key in args.scenario or sorted(SCENARIOS) + VARIANTS:
        if key == INJECTION_KEY:  # cash_crunch with attacks in its imported text (4d)
            business = prompt_injection_variant(generate(SCENARIOS["cash_crunch"], args.seed))
        elif key == MESSY_KEY:  # cash_crunch with planted bookkeeping errors (15)
            business = messy_books_variant(generate(SCENARIOS["cash_crunch"], args.seed))
            business.write(args.out / key)
            print(
                f"{key}: {len(business.ground_truth['planted'])} planted errors -> {args.out / key}"
            )
            continue
        else:
            business = generate(SCENARIOS[key], seed=args.seed)
        business.write(args.out / key)
        forward = business.ground_truth["forward"]["low_point"]
        print(
            f"{key}: {len(business.tables['transactions.csv'][1])} transactions, "
            f"forward low {forward['balance']} on {forward['date']} (week {forward['week']}) "
            f"-> {args.out / key}"
        )


if __name__ == "__main__":
    main()
