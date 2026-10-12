"""One real call to Claude (costs about a cent). Skipped unless RUN_LIVE=1 and a key is set.

    RUN_LIVE=1 pytest -m live

The default `pytest` run deselects this (pyproject addopts), so CI and judges stay offline.
"""

import os
from decimal import Decimal

import pytest

from copilot.agent import handle
from copilot.agent.claude import has_api_key
from copilot.runtime import SCENARIOS, make_llm, open_scenario
from copilot.schemas import Role

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE") != "1" or not has_api_key(),
        reason="set RUN_LIVE=1 and ANTHROPIC_API_KEY to call the real model",
    ),
]

CASH_CRUNCH = SCENARIOS["Straits Harbour Distribution (cash crunch)"]


def test_cash_question_uses_the_tool_and_quotes_its_number():
    s = open_scenario(CASH_CRUNCH, Role.OWNER, llm=make_llm("claude"))
    truth = s.gateway.call(s.actor, "get_cash_position", {}).for_llm()["data"]["value"]["total"]
    reply = handle("How much cash do we have right now, in total?", s)
    assert "get_cash_position" in [t.tool for t in reply.trace]
    assert f"{Decimal(truth):,.2f}" in reply.text
    assert s.llm.usage.calls >= 2
