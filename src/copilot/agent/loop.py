"""agent.handle(message, session): the single entry point the UI calls.

Order matters for security:
1. The user's message is checked against a pending action BEFORE the LLM sees it, so only the
   user's own words can confirm, and the LLM never decides whether something was confirmed.
2. The LLM may then call tools, but only through the policy gateway, for at most MAX_STEPS
   rounds. It gets tool results with external text wrapped and without confirmation codes.
3. Anything the system itself must tell the user (payment results, the confirmation prompt)
   is returned separately from the LLM's text, so the LLM can't alter or fake it.
4. The LLM's final text passes the output guard (agent/output_guard.py) before the user, or
   the conversation history, sees it. Every intervention is audited.
"""

from __future__ import annotations

import json
import re

from copilot.agent.llm import Message, ToolCall
from copilot.agent.output_guard import guard_reply
from copilot.agent.prompts import build_system_prompt
from copilot.agent.state import AgentReply, Session, TraceStep
from copilot.untrusted import wrap_untrusted

MAX_STEPS = 6
MAX_MESSAGE_CHARS = 4000

# After a cancellation, these replies were only about the pending action: don't send them on.
_ONLY_ABOUT_PENDING = re.compile(
    r"\s*(yes|y|yeah|yep|ok|okay|sure|no|n|nope|cancel|stop|don'?t|confirm\b.*)\s*[.!]?\s*",
    re.IGNORECASE,
)

_CODE = re.compile(r"(\bconfirm\s*#?\s*)\d{4}\b", re.IGNORECASE)

FALLBACK = (
    "Sorry, I couldn't complete that. Nothing was changed. Please try again or ask in a "
    "different way."
)
STEP_LIMIT = (
    "Sorry, that took more steps than I'm allowed, so I stopped. Nothing further was changed. "
    "Could you break the request into smaller parts?"
)


def handle(message: str, session: Session) -> AgentReply:
    text = message.strip()
    if not text:
        return AgentReply(text="Please type a question or request.")
    if len(text) > MAX_MESSAGE_CHARS:
        return AgentReply(
            text=f"That message is too long (over {MAX_MESSAGE_CHARS:,} characters). "
            "Please shorten it."
        )

    actor, gateway = session.actor, session.gateway
    notices: list[str] = []

    resolution = gateway.on_user_message(actor, text)
    remembered = _hide_code(text)  # the model never sees a code, even a used one
    if resolution is not None:
        notices.append(resolution.message)
        session.history.append(Message(role="user", content=remembered))
        # The notice can quote external text (a customer's name, a bill number): label it.
        notice = f"[System] {wrap_untrusted(resolution.message)}"
        session.history.append(Message(role="assistant", content=notice))
        if resolution.outcome != "cancelled" or _ONLY_ABOUT_PENDING.fullmatch(text):
            return AgentReply(text="", notices=tuple(notices))
        # The message also asks something new: the model answers it, and keeps the notice so it
        # knows the action was cancelled (it once told the user it was "still queued").

    session.history.append(Message(role="user", content=remembered))
    system = build_system_prompt(
        session.business_name, gateway.today(actor), actor.role, session.canary
    )
    tools = gateway.specs(actor)
    trace: list[TraceStep] = []
    pending_prompt: str | None = None

    for _ in range(MAX_STEPS):
        try:
            response = session.llm.complete(system, list(session.history), tools)
        except Exception:  # provider boundary: any failure becomes a safe fallback
            session.history.append(Message(role="assistant", content=FALLBACK))
            return _reply(FALLBACK, notices, pending_prompt, trace)

        guarded = guard_reply(response.text, system, session.canary)
        for outcome, detail in guarded.events:
            gateway.record(actor, outcome, detail)
        # The provider's raw reply goes back verbatim only if the guard changed nothing: a
        # blocked or rewritten reply must not reach the model again through the raw copy.
        raw = response.raw if guarded.text == response.text else None
        session.history.append(
            Message(
                role="assistant",
                content=guarded.text,
                tool_calls=response.tool_calls,
                provider_blocks=raw,
            )
        )
        if not response.tool_calls:
            return _reply(guarded.text, notices, pending_prompt, trace)

        for call in response.tool_calls:
            result = gateway.call(actor, call.name, call.arguments)
            trace.append(TraceStep(tool=call.name, outcome=result.outcome))
            if result.pending is not None:
                pending_prompt = result.pending.prompt
            session.history.append(_tool_message(call, result.for_llm()))

    session.history.append(Message(role="assistant", content=STEP_LIMIT))
    return _reply(STEP_LIMIT, notices, pending_prompt, trace)


def _hide_code(text: str) -> str:
    return _CODE.sub(r"\1****", text)


def _tool_message(call: ToolCall, payload: dict) -> Message:
    return Message(
        role="tool",
        content=json.dumps(payload, ensure_ascii=False),
        tool_call_id=call.id,
    )


def _reply(
    text: str, notices: list[str], pending_prompt: str | None, trace: list[TraceStep]
) -> AgentReply:
    return AgentReply(
        text=text, notices=tuple(notices), pending_prompt=pending_prompt, trace=tuple(trace)
    )
