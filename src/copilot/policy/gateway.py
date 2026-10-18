"""The only way the agent reaches a tool.

Gateway.call(actor, tool, args), for every tool call the LLM makes:
  1. unknown tool or arguments that fail validation -> invalid
  2. role below the tool's minimum -> denied
  3. read tool -> run it, return the result
  4. write tool -> run its guard (blocked if any reason) -> restate it in code ->
     needs confirmation ? create a pending action : run it now
Gateway.on_user_message(actor, message), called by the orchestrator on every user message
BEFORE the LLM sees it: if an action is pending, the message either confirms it (exactly
"confirm <code>") and it runs after the guard is re-checked, or cancels it.
Gateway.advance_clock(actor, days): the demo's simulated clock (policy/scheduler.py). Not a
tool, so the LLM can't call it; scheduled payments that come due are re-checked before they run.
Every step is written to the audit log.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from pydantic import ValidationError

from copilot.policy.audit import AuditLog, AuditOutcome
from copilot.policy.confirmations import Confirmations, PendingAction
from copilot.policy.guards import GUARDS
from copilot.policy.roles import Actor, has_role
from copilot.policy.scheduler import ClockReport, advance
from copilot.sandbox.bank import Sandbox
from copilot.sandbox.world import WorldScript
from copilot.schemas import CopilotModel
from copilot.store import NotFoundError, Store
from copilot.tools import default_registry
from copilot.tools.registry import Tool, ToolContext, ToolRegistry, WriteOutcome
from copilot.tools.render import flagged_paths, to_llm
from copilot.untrusted import wrap_untrusted

_MAX_FLAGGED_PATHS = 20

# Business failures a tool may raise; anything else is a bug and is allowed to surface.
_EXPECTED_ERRORS = (NotFoundError, ValueError, sqlite3.IntegrityError)


class ToolResult(CopilotModel):
    tool: str
    ok: bool
    outcome: AuditOutcome
    message: str
    data: Any = None
    pending: PendingAction | None = None  # for the UI; never shown to the LLM

    def for_llm(self) -> dict[str, Any]:
        """What the LLM sees: no confirmation code, external text wrapped.

        Messages are written by code but can quote external text (a refusal names the bill
        number, a result names the customer), so they are wrapped too. The one exception is
        the fixed instruction sent with a pending action, which quotes nothing.
        """
        message = self.message if self.outcome == "pending" else wrap_untrusted(self.message)
        return {
            "tool": self.tool,
            "ok": self.ok,
            "outcome": self.outcome,
            "message": message,
            "data": to_llm(self.data),
        }


class Resolution(CopilotModel):
    """What happened to a pending action after the user's next message."""

    action: PendingAction
    outcome: AuditOutcome
    message: str
    data: Any = None


class Gateway:
    def __init__(
        self,
        store: Store,
        sandbox: Sandbox,
        registry: ToolRegistry | None = None,
        world: WorldScript | None = None,
    ) -> None:
        self.store = store
        self.sandbox = sandbox
        self.registry = registry or default_registry()
        self.world = world or WorldScript()
        self.audit = AuditLog(store, sandbox)
        self.confirmations = Confirmations(store)

    def specs(self, actor: Actor) -> list[dict[str, Any]]:
        return self.registry.specs_for(actor.role)

    def today(self, actor: Actor) -> date:
        """The simulated date for the actor's business (for the system prompt and the UI)."""
        return self.sandbox.today(actor.business_id)

    def pending(self, actor: Actor) -> PendingAction | None:
        """This session's action awaiting confirmation, if any (for the UI)."""
        return self.confirmations.current(actor)

    def record(self, actor: Actor, outcome: AuditOutcome, detail: str) -> None:
        """Audit an output-guard intervention on the assistant's reply (not a tool call)."""
        self.audit.log(actor, "output_guard", "reply", {}, outcome, detail)

    def advance_clock(self, actor: Actor, days: int) -> ClockReport:
        """Move the simulated clock forward (demo control, any signed-in role)."""
        return advance(self.store, self.sandbox, self.world, self.audit, actor, days)

    # --- Tool calls -----------------------------------------------------------

    def call(self, actor: Actor, name: str, raw_args: Any) -> ToolResult:
        tool = self.registry.get(name)
        if tool is None:
            return self._finish(actor, name, "unknown", raw_args, "invalid", f"unknown tool {name}")
        if not has_role(actor, tool.min_role):
            return self._finish(
                actor,
                name,
                tool.kind,
                raw_args,
                "denied",
                f"needs the {tool.min_role.label} role; you are {actor.role.label}",
            )
        try:
            args = tool.input_model.model_validate(raw_args)
        except ValidationError as exc:
            return self._finish(actor, name, tool.kind, raw_args, "invalid", _short(exc))
        params = args.model_dump(mode="json")
        ctx = self._ctx(actor)

        if tool.kind == "read":
            try:
                data = tool.run(ctx, args)
            except _EXPECTED_ERRORS as exc:
                return self._finish(actor, name, "read", params, "error", _error(exc))
            result = self._finish(actor, name, "read", params, "ok", "ok", data=data)
            self._audit_flagged(actor, name, data)
            return result

        reasons = self._guard(ctx, tool, args)
        if reasons:
            return self._finish(actor, name, "write", params, "blocked", "; ".join(reasons))
        try:
            summary = tool.describe(ctx, args)  # type: ignore[misc]
        except _EXPECTED_ERRORS as exc:
            return self._finish(actor, name, "write", params, "error", _error(exc))

        if not tool.needs_confirmation:
            return self._run_write(actor, tool, ctx, args, params)

        action, replaced = self.confirmations.propose(actor, name, params, summary)
        if replaced is not None:
            self.audit.log(
                actor,
                replaced.tool,
                "write",
                replaced.params,
                "cancelled",
                "replaced by a newer request",
            )
        self.audit.log(actor, name, "write", params, "pending", f"awaiting code ({action.id})")
        return ToolResult(
            tool=name,
            ok=True,
            outcome="pending",
            message=(
                "Not done yet. The exact details and a confirmation code have been shown to "
                "the user, who must reply with that code. Do not ask for, repeat or guess the "
                "code, and do not say the action has happened."
            ),
            data=args,
            pending=action,
        )

    # --- Confirmation -----------------------------------------------------------

    def on_user_message(self, actor: Actor, message: str) -> Resolution | None:
        """Resolve this session's pending action, if any, with the user's own message."""
        taken = self.confirmations.take(actor, message)
        if taken is None:
            return None
        action, confirmed = taken
        if not confirmed:
            self.audit.log(
                actor,
                action.tool,
                "write",
                action.params,
                "cancelled",
                "next message was not the confirmation code",
            )
            return Resolution(
                action=action,
                outcome="cancelled",
                message=f"Cancelled, nothing done: {action.summary}",
            )

        tool = self.registry.get(action.tool)
        if tool is None or not has_role(actor, tool.min_role):
            self.audit.log(actor, action.tool, "write", action.params, "denied", "role changed")
            return Resolution(action=action, outcome="denied", message="Not allowed any more.")
        self.audit.log(actor, action.tool, "write", action.params, "confirmed", action.id)
        args = tool.input_model.model_validate(action.params)
        ctx = self._ctx(actor)
        reasons = self._guard(ctx, tool, args)
        if reasons:
            reason = "; ".join(reasons)
            self.audit.log(actor, action.tool, "write", action.params, "blocked", reason)
            return Resolution(action=action, outcome="blocked", message=f"Blocked: {reason}.")
        result = self._run_write(actor, tool, ctx, args, action.params)
        return Resolution(
            action=action, outcome=result.outcome, message=result.message, data=result.data
        )

    # --- internals --------------------------------------------------------------

    def _audit_flagged(self, actor: Actor, tool: str, data: Any) -> None:
        """Record instruction-like external text that a read handed to the LLM (paths only)."""
        paths = flagged_paths(to_llm(data))
        if paths:
            self.audit.log(
                actor,
                "injection_scan",
                "read",
                {"tool": tool, "fields": paths[:_MAX_FLAGGED_PATHS], "count": len(paths)},
                "flagged",
                f"{len(paths)} instruction-like value(s) in the {tool} result, shown as data",
            )

    def _ctx(self, actor: Actor) -> ToolContext:
        return ToolContext(
            store=self.store,
            sandbox=self.sandbox,
            business_id=actor.business_id,
            user_id=actor.user_id,
        )

    def _guard(self, ctx: ToolContext, tool: Tool, args: Any) -> list[str]:
        guard = GUARDS.get(tool.name)
        if guard is None:
            return ["no policy guard is defined for this action"]  # fail closed
        return guard(ctx.store, ctx.sandbox, ctx.business_id, args)

    def _run_write(
        self, actor: Actor, tool: Tool, ctx: ToolContext, args: Any, params: dict[str, Any]
    ) -> ToolResult:
        try:
            outcome: WriteOutcome = tool.run(ctx, args)
        except _EXPECTED_ERRORS as exc:
            return self._finish(actor, tool.name, "write", params, "error", _error(exc))
        return self._finish(
            actor,
            tool.name,
            "write",
            params,
            outcome.outcome,
            outcome.message,
            data=outcome.data,
            ok=outcome.outcome != "rejected",
        )

    def _finish(
        self,
        actor: Actor,
        name: str,
        kind: str,
        params: Any,
        outcome: AuditOutcome,
        message: str,
        data: Any = None,
        ok: bool | None = None,
    ) -> ToolResult:
        self.audit.log(actor, name, kind, params, outcome, None if outcome == "ok" else message)
        return ToolResult(
            tool=name,
            ok=ok if ok is not None else outcome in ("ok", "saved", "executed", "scheduled"),
            outcome=outcome,
            message=message,
            data=data,
        )


def _short(exc: ValidationError) -> str:
    """Validation errors without echoing the submitted values back."""
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()
    )


def _error(exc: Exception) -> str:
    if isinstance(exc, NotFoundError):
        return f"not found: {exc}"
    return str(exc)
