"""The LLM provider interface and the scripted mock used by tests.

Messages and tool calls use the provider-neutral types below. A real provider
(agent/claude.py) converts to and from its own API format inside its adapter; nothing else changes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Any  # whatever the model produced; the gateway validates it


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None  # for role="tool": which call this answers
    # role="assistant": the provider's raw reply, echoed back verbatim on the next call (Claude's
    # signed thinking must not change). Opaque to everything except the provider adapter.
    provider_blocks: Any = None


@dataclass(frozen=True)
class LLMResponse:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    raw: Any = None  # provider-owned; stored as Message.provider_blocks if the reply is unchanged


class LLM(Protocol):
    name: str

    def complete(
        self, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMResponse: ...


@dataclass
class Call:
    """One request the agent made to the LLM (recorded by ScriptedLLM for assertions)."""

    system: str
    messages: list[Message]
    tools: list[dict[str, Any]]


Step = LLMResponse | Callable[[Call], LLMResponse]


@dataclass
class ScriptedLLM:
    """Replays the responses a test lists, in order. A step may be a function of the call."""

    steps: list[Step]
    name: str = "scripted mock"
    calls: list[Call] = field(default_factory=list)

    def complete(
        self, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        call = Call(system=system, messages=list(messages), tools=list(tools))
        self.calls.append(call)
        if not self.steps:
            raise RuntimeError("ScriptedLLM has no more responses")
        step = self.steps.pop(0)
        return step(call) if callable(step) else step
