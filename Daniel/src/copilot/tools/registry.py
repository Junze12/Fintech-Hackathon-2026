"""The tool interface: what every tool declares, and the catalogue the agent is shown.

A Tool declares its name (verb_noun), a description written for the LLM, a strict input model,
the minimum role it needs and whether it reads or writes. Tools never check permissions
themselves and are never called by the agent directly: the only caller is
policy.gateway.Gateway, which validates arguments, checks the role, runs guards, asks for
confirmation and audits every call (CLAUDE.md rule 5).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from copilot.sandbox.bank import Sandbox
from copilot.schemas import CopilotModel, Role
from copilot.store import Store

ToolKind = Literal["read", "write"]


class ToolInput(BaseModel):
    """Base for tool arguments. Unknown fields (e.g. role, business_id) are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")


@dataclass(frozen=True)
class ToolContext:
    """What a tool runs against. business_id and user_id come from the session, never arguments."""

    store: Store
    sandbox: Sandbox
    business_id: str
    user_id: str = ""  # the signed-in user, for personal settings such as the alert floor


WriteStatus = Literal["executed", "scheduled", "saved", "rejected"]


class WriteOutcome(CopilotModel):
    """What happened when a write tool ran."""

    outcome: WriteStatus
    message: str
    data: Any = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[ToolInput]
    min_role: Role
    kind: ToolKind
    # read: returns the result. write: performs the action and returns a WriteOutcome.
    run: Callable[[ToolContext, Any], Any]
    # write only: plain-language restatement of exactly what run() will do, built by code.
    describe: Callable[[ToolContext, Any], str] | None = None
    needs_confirmation: bool = False
    # Moves money, changes the books or reaches someone outside the business. Such a tool
    # must need the user's confirmation (checked at registration).
    external_effect: bool = False

    def spec(self) -> dict[str, Any]:
        """Definition handed to the LLM: name, description and JSON schema of the arguments."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name} is already registered")
        if tool.input_model.model_config.get("extra") != "forbid":
            raise ValueError(f"{tool.name}: input model must forbid unknown fields")
        if tool.kind == "write" and tool.describe is None:
            raise ValueError(f"{tool.name}: write tools must describe what they will do")
        if tool.kind == "read" and (tool.needs_confirmation or tool.external_effect):
            raise ValueError(f"{tool.name}: read tools don't need confirmation")
        if tool.external_effect and not tool.needs_confirmation:
            raise ValueError(f"{tool.name}: a tool with an external effect must be confirmed")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def specs_for(self, role: Role) -> list[dict[str, Any]]:
        """Only the tools this role may use, so the LLM isn't even offered the others."""
        return [t.spec() for t in self._tools.values() if role >= t.min_role]
