"""Audit log: every tool call and every write attempt, allowed or not (CLAUDE.md rule 9).

Each entry records who (user, role, session), what (tool, read/write, parameters with account
numbers masked), when (simulated date and wall-clock time in SGT) and the outcome with the
reason if it was refused. It is the main source for the execution-evidence export.

Tamper-evident: each row stores the SHA-256 hash of its own content plus the previous row's hash
(one chain per business). verify_chain() recomputes the chain, so editing, deleting or
reordering a row is detected. Deleting the newest rows can only be detected against a head hash
recorded earlier (the evidence export prints it); see known-risks.md.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Literal

from pydantic import SecretStr

from copilot.policy.roles import Actor
from copilot.sandbox.bank import Sandbox
from copilot.schemas import SGT, CopilotModel, Id, Role, Timestamp, mask, mask_account_like
from copilot.store import Store

AuditOutcome = Literal[
    "ok",  # read tool answered
    "invalid",  # unknown tool or bad arguments
    "denied",  # role too low
    "blocked",  # a policy guard refused it
    "pending",  # write proposed, waiting for the user's confirmation
    "confirmed",  # the user confirmed with the right code
    "cancelled",  # the user's next message was not a valid confirmation
    "executed",  # money moved / record changed in the sandbox
    "scheduled",  # payment accepted for a future date
    "saved",  # a draft was saved
    "rejected",  # the sandbox refused it (e.g. insufficient funds)
    "error",  # not found or an unexpected failure
    "flagged",  # a read result carried instruction-like external text (shown as data)
    "redacted",  # the output guard masked something in the assistant's reply
    "output_blocked",  # the output guard replaced the assistant's reply
]

_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    sim_date TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    tool TEXT NOT NULL,
    kind TEXT NOT NULL,
    params TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT,
    prev_hash TEXT NOT NULL,
    row_hash TEXT NOT NULL
)
"""

GENESIS = "0" * 64
_HASHED = (
    "business_id",
    "session_id",
    "user_id",
    "role",
    "sim_date",
    "logged_at",
    "tool",
    "kind",
    "params",
    "outcome",
    "reason",
)


class AuditEntry(CopilotModel):
    seq: int
    business_id: Id
    session_id: Id
    user_id: Id
    role: Role
    sim_date: date
    logged_at: Timestamp
    tool: str
    kind: str
    params: dict[str, Any]
    outcome: AuditOutcome
    reason: str | None = None
    row_hash: str


class ChainCheck(CopilotModel):
    ok: bool
    entries: int
    head: str  # hash of the newest row (GENESIS if empty); record it to detect tail deletion
    first_bad_seq: int | None = None
    problem: str | None = None


def _row_hash(values: dict[str, Any], prev_hash: str) -> str:
    content = json.dumps([values[k] for k in _HASHED] + [prev_hash], ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def mask_value(value: Any, key: str = "") -> Any:
    """JSON-safe copy of value with account numbers masked (••••1234)."""
    if isinstance(value, SecretStr):
        return mask(value)
    if isinstance(value, dict):
        return {str(k): mask_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [mask_value(v, key) for v in value]
    if isinstance(value, str):
        if "account_number" in key:
            return mask(value)
        return mask_account_like(value)
    if value is None or isinstance(value, bool | int):
        return value
    return str(value)  # Decimal, date, enums: stored as text, never as float


class AuditLog:
    def __init__(self, store: Store, sandbox: Sandbox) -> None:
        self.store = store
        self.sandbox = sandbox
        store.conn.execute(_AUDIT_TABLE)

    def log(
        self,
        actor: Actor,
        tool: str,
        kind: str,
        params: Any,
        outcome: AuditOutcome,
        reason: str | None = None,
    ) -> int:
        safe = mask_value(params if isinstance(params, dict) else {"raw": params})
        values = {
            "business_id": actor.business_id,
            "session_id": actor.session_id,
            "user_id": actor.user_id,
            "role": actor.role.label,
            "sim_date": self.sandbox.today(actor.business_id).isoformat(),
            "logged_at": datetime.now(SGT).isoformat(),
            "tool": tool,
            "kind": kind,
            "params": json.dumps(safe, ensure_ascii=False, sort_keys=True),
            "outcome": outcome,
            "reason": reason,
        }
        with self.store.transaction():  # read the previous hash and append atomically
            prev = self.head(actor.business_id)
            cursor = self.store.conn.execute(
                f"INSERT INTO audit_log ({', '.join(_HASHED)}, prev_hash, row_hash) "
                f"VALUES ({', '.join('?' * (len(_HASHED) + 2))})",
                (*values.values(), prev, _row_hash(values, prev)),
            )
        return int(cursor.lastrowid or 0)

    def head(self, business_id: str) -> str:
        row = self.store.conn.execute(
            "SELECT row_hash FROM audit_log WHERE business_id = ? ORDER BY seq DESC LIMIT 1",
            (business_id,),
        ).fetchone()
        return row["row_hash"] if row is not None else GENESIS

    def verify_chain(self, business_id: str) -> ChainCheck:
        """Recompute this business's chain from the first row. Any edit, deletion or reordering
        breaks it at the first affected row."""
        rows = self.store.conn.execute(
            "SELECT * FROM audit_log WHERE business_id = ? ORDER BY seq", (business_id,)
        ).fetchall()
        prev = GENESIS
        for r in rows:
            if r["prev_hash"] != prev:
                return ChainCheck(
                    ok=False,
                    entries=len(rows),
                    head=prev,
                    first_bad_seq=r["seq"],
                    problem="the row before this one was removed or reordered",
                )
            if _row_hash(dict(r), prev) != r["row_hash"]:
                return ChainCheck(
                    ok=False,
                    entries=len(rows),
                    head=prev,
                    first_bad_seq=r["seq"],
                    problem="this row was changed after it was written",
                )
            prev = r["row_hash"]
        return ChainCheck(ok=True, entries=len(rows), head=prev)

    def entries(self, business_id: str) -> list[AuditEntry]:
        rows = self.store.conn.execute(
            "SELECT * FROM audit_log WHERE business_id = ? ORDER BY seq", (business_id,)
        )
        return [
            AuditEntry(
                seq=r["seq"],
                business_id=r["business_id"],
                session_id=r["session_id"],
                user_id=r["user_id"],
                role=Role[r["role"].upper()],
                sim_date=date.fromisoformat(r["sim_date"]),
                logged_at=datetime.fromisoformat(r["logged_at"]),
                tool=r["tool"],
                kind=r["kind"],
                params=json.loads(r["params"]),
                outcome=r["outcome"],
                reason=r["reason"],
                row_hash=r["row_hash"],
            )
            for r in rows
        ]
