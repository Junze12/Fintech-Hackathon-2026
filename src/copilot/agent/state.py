"""Conversation state: who is talking, through which gate, to which model, and what was said."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from copilot.agent.llm import LLM, Message
from copilot.policy.gateway import Gateway
from copilot.policy.roles import Actor


@dataclass
class Session:
    actor: Actor  # from sign-in, never from chat
    gateway: Gateway
    llm: LLM
    business_name: str
    history: list[Message] = field(default_factory=list)
    # Random marker in this session's system prompt; a reply containing it is blocked.
    canary: str = field(default_factory=lambda: f"cnry-{secrets.token_hex(8)}")


@dataclass(frozen=True)
class TraceStep:
    tool: str
    outcome: str


@dataclass(frozen=True)
class AgentReply:
    text: str  # the assistant's words
    notices: tuple[str, ...] = ()  # written by the system, not the LLM (e.g. payment result)
    pending_prompt: str | None = None  # restatement + "Reply 'confirm 1234'"; shown by the UI
    trace: tuple[TraceStep, ...] = ()
