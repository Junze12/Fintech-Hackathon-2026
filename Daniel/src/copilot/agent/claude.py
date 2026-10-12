"""Claude as the agent's LLM (CLAUDE.md rule 8): the only file that knows Anthropic's API.

It converts the provider-neutral Message / ToolCall / LLMResponse types (agent/llm.py) to and
from the Messages API. Nothing else in the code base imports `anthropic`.

Settings (environment variables, or `.env` at the repo root; a real env var wins):
    ANTHROPIC_API_KEY   required; never logged, printed or audited
    COPILOT_MODEL       default claude-sonnet-5-5
    COPILOT_EFFORT      default medium (low | medium | high | xhigh | max)

Request choices (docs/technical/architecture.md -> "The Claude backend"):
- Prompt caching, two breakpoints: one on the last tool (the ~5-6k-token tool list is the same
  for every session with the same role, so later sessions read it at 0.1x instead of rewriting
  it; the system prompt holds a per-session canary and can't be shared), and top-level
  automatic caching for the growing conversation.
- Adaptive thinking. Sonnet 5.5 signs its thinking blocks, which must come back unchanged on the
  next step. The raw assistant content is kept in `LLMResponse.raw` / `Message.provider_blocks`
  and echoed verbatim. If history did change (the loop's output guard rewrote a reply, or the
  date in the system prompt moved), `drop_block` makes the API drop the stale reasoning
  instead of failing the request.
- `fallbacks="default"`: a refused request is retried server-side on another model. A refusal
  that remains becomes a polite reply, never a crash.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from copilot.agent.llm import LLMResponse, Message, ToolCall

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "medium"
MAX_TOKENS = 16000
TIMEOUT_SECONDS = 60.0
BETAS = ["thinking-binding-controls-2026-08-01", "server-side-fallback-2026-07-01"]

# US$ per million tokens, Claude Sonnet 5.5 (for the eval's cost line only).
PRICE_PER_MTOK = {"input": 2.00, "cache_write": 2.50, "cache_read": 0.20, "output": 10.00}

REFUSED = "Sorry, I can't help with that request. Nothing was changed."

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODEL_NAMES = {"claude-sonnet-5-5": "Claude Sonnet 5.5", "claude-opus-5-5": "Claude Opus 5.5"}


def load_env() -> None:
    """Read `.env` at the repo root into the environment, without overriding real env vars."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # the "llm" extra isn't installed: only real env vars count
        return
    load_dotenv(_REPO_ROOT / ".env", override=False)


def has_api_key() -> bool:
    load_env()
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


class ResponseTruncated(RuntimeError):
    """The reply hit max_tokens; the loop turns any provider error into its safe fallback."""


@dataclass
class Usage:
    calls: int = 0
    input: int = 0
    cache_write: int = 0
    cache_read: int = 0
    output: int = 0

    def add(self, usage: Any) -> None:
        self.calls += 1
        self.input += getattr(usage, "input_tokens", 0) or 0
        self.cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.output += getattr(usage, "output_tokens", 0) or 0

    def merge(self, other: Usage) -> None:
        for name in ("calls", "input", "cache_write", "cache_read", "output"):
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def cost_usd(self) -> float:
        return sum(getattr(self, k) * p for k, p in PRICE_PER_MTOK.items()) / 1_000_000


@dataclass
class ClaudeLLM:
    model: str = ""
    effort: str = ""
    client: Any = None  # injected in tests; built from the environment otherwise
    usage: Usage = field(default_factory=Usage)

    def __post_init__(self) -> None:
        load_env()
        self.model = self.model or os.environ.get("COPILOT_MODEL", DEFAULT_MODEL)
        self.effort = self.effort or os.environ.get("COPILOT_EFFORT", DEFAULT_EFFORT)
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS, max_retries=2)

    @property
    def name(self) -> str:
        return _MODEL_NAMES.get(self.model, self.model)

    def __repr__(self) -> str:  # the client holds the key: keep it out of reprs and logs
        return f"ClaudeLLM(model={self.model!r}, effort={self.effort!r})"

    def complete(
        self, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=with_tool_breakpoint(tools),
            messages=to_api_messages(messages),
            output_config={"effort": self.effort},
            thinking={
                "type": "adaptive",
                "block_binding": {"prefix_mismatch_behavior": "drop_block"},
            },
            cache_control={"type": "ephemeral"},
            fallbacks="default",
            betas=BETAS,
        )
        self.usage.add(response.usage)
        return from_api_response(response)


def with_tool_breakpoint(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A copy of the tool list with a cache breakpoint on its last tool (specs left untouched)."""
    if not tools:
        return tools
    return [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}]


def to_api_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Neutral history -> Messages API turns. Consecutive tool results share one user turn."""
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
            last = out[-1] if out else None
            if last and last["role"] == "user" and _all_tool_results(last["content"]):
                last["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        elif m.role == "assistant":
            out.append({"role": "assistant", "content": _assistant_blocks(m)})
        else:
            out.append({"role": "user", "content": [{"type": "text", "text": m.content}]})
    return out


def _assistant_blocks(m: Message) -> list[dict[str, Any]]:
    if m.provider_blocks:
        return list(m.provider_blocks)  # verbatim: signed thinking must not change
    blocks: list[dict[str, Any]] = []
    if m.content:  # an empty text block is rejected by the API
        blocks.append({"type": "text", "text": m.content})
    for call in m.tool_calls:
        blocks.append(
            {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
        )
    return blocks or [{"type": "text", "text": "(no reply)"}]


def _all_tool_results(content: Any) -> bool:
    return isinstance(content, list) and all(b.get("type") == "tool_result" for b in content)


def from_api_response(response: Any) -> LLMResponse:
    if response.stop_reason == "refusal":
        return LLMResponse(text=REFUSED)
    if response.stop_reason == "max_tokens":
        raise ResponseTruncated("reply hit max_tokens")
    texts: list[str] = []
    calls: list[ToolCall] = []
    for block in response.content:
        if block.type == "text":
            texts.append(block.text)
        elif block.type == "tool_use":
            calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
    raw = tuple(_as_dict(b) for b in response.content)
    return LLMResponse(text="\n\n".join(t for t in texts if t), tool_calls=tuple(calls), raw=raw)


def _as_dict(block: Any) -> dict[str, Any]:
    return block.to_dict() if hasattr(block, "to_dict") else dict(block)
