"""Pending actions and the confirmation check.

A write that needs confirmation becomes a pending action with a random 4-digit code. It runs
only if the user's own next message is exactly "confirm <code>". Any other next message
cancels it. This check is plain code on the user's message: the LLM never decides whether
something was confirmed, and it is never shown the code.

One pending action per session at a time; proposing a new one replaces the old one.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from typing import Any
from uuid import uuid4

from copilot.policy.roles import Actor
from copilot.schemas import SGT, CopilotModel, Id, Timestamp
from copilot.store import Store

_PENDING_TABLE = """
CREATE TABLE IF NOT EXISTS pending_actions (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tool TEXT NOT NULL,
    params TEXT NOT NULL,
    code TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL
)
"""
# The database itself guarantees at most one pending action per session.
_ONE_PER_SESSION = (
    "CREATE UNIQUE INDEX IF NOT EXISTS one_pending_per_session "
    "ON pending_actions(session_id) WHERE status = 'pending'"
)

_CONFIRM = re.compile(r"\s*confirm\s+(\d{4})\s*[.!]?\s*", re.IGNORECASE)


class PendingAction(CopilotModel):
    id: Id
    business_id: Id
    session_id: Id
    user_id: Id
    tool: str
    params: dict[str, Any]
    code: str
    summary: str  # restatement built by code, shown to the user verbatim
    created_at: Timestamp

    @property
    def prompt(self) -> str:
        """What the UI shows the user, outside the LLM's own reply."""
        return f"{self.summary} Reply 'confirm {self.code}' to proceed; anything else cancels."


def is_confirmation(message: str, code: str) -> bool:
    match = _CONFIRM.fullmatch(message)
    return match is not None and secrets.compare_digest(match.group(1), code)


class Confirmations:
    def __init__(self, store: Store) -> None:
        self.store = store
        store.conn.execute(_PENDING_TABLE)
        store.conn.execute(_ONE_PER_SESSION)

    def propose(
        self, actor: Actor, tool: str, params: dict[str, Any], summary: str
    ) -> tuple[PendingAction, PendingAction | None]:
        """Create a pending action. Returns it and the one it replaced, if any."""
        action = PendingAction(
            id=f"pa-{uuid4().hex[:12]}",
            business_id=actor.business_id,
            session_id=actor.session_id,
            user_id=actor.user_id,
            tool=tool,
            params=params,
            code=f"{secrets.randbelow(10_000):04d}",
            summary=summary,
            created_at=datetime.now(SGT),
        )
        with self.store.transaction():
            replaced = self._current(actor.session_id)
            if replaced is not None:
                self._set_status(replaced.id, "superseded")
            self.store.conn.execute(
                "INSERT INTO pending_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
                (
                    action.id,
                    action.business_id,
                    action.session_id,
                    action.user_id,
                    action.tool,
                    json.dumps(action.params),
                    action.code,
                    action.summary,
                    action.created_at.isoformat(),
                ),
            )
        return action, replaced

    def current(self, actor: Actor) -> PendingAction | None:
        action = self._current(actor.session_id)
        if action is None or not self._owned_by(action, actor):
            return None
        return action

    def take(self, actor: Actor, message: str) -> tuple[PendingAction, bool] | None:
        """Consume this session's pending action using the user's next message.

        Returns None if nothing is pending; otherwise the action and whether the message
        confirmed it. Either way the action is no longer pending afterwards, so it can never
        run twice.
        """
        action = self.current(actor)
        if action is None:
            return None
        confirmed = is_confirmation(message, action.code)
        if not self._set_status(action.id, "confirmed" if confirmed else "cancelled"):
            return None  # someone else consumed it first
        return action, confirmed

    # --- internals ------------------------------------------------------------

    def _current(self, session_id: str) -> PendingAction | None:
        row = self.store.conn.execute(
            "SELECT * FROM pending_actions WHERE session_id = ? AND status = 'pending'",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return PendingAction(
            id=row["id"],
            business_id=row["business_id"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            tool=row["tool"],
            params=json.loads(row["params"]),
            code=row["code"],
            summary=row["summary"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _owned_by(action: PendingAction, actor: Actor) -> bool:
        return action.business_id == actor.business_id and action.user_id == actor.user_id

    def _set_status(self, action_id: str, status: str) -> bool:
        cursor = self.store.conn.execute(
            "UPDATE pending_actions SET status = ? WHERE id = ? AND status = 'pending'",
            (status, action_id),
        )
        return cursor.rowcount == 1
