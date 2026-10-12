"""Red-team suite (deliverable #4 test cases, feeds the security self-assessment).

Every YAML case in this folder runs twice:
- with the fooled model: a scripted model that falls for the attack, so the case checks the
  structural defences (gateway, confirmation, output guard, wrapping) and its own expectations;
- with the rule-based mock: the universal safety checks only.
Chunk 5 re-runs the same cases against the real model: python scripts/run_eval.py --llm claude.
"""

import pytest

from copilot.agent.mock_rules import RuleBasedLLM
from copilot.evals.redteam import THREATS, load_cases, run_case

CASES = load_cases()


def test_every_threat_has_cases():
    assert {c.threat for c in CASES} == set(THREATS)
    assert len(CASES) >= 20


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_defence_holds_against_a_fooled_model(case):
    result = run_case(case)
    assert result.passed, "\n".join(result.failures)


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_mock_model_stays_safe(case):
    result = run_case(case, RuleBasedLLM())
    assert result.passed, "\n".join(result.failures)
