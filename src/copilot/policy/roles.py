"""Who is acting, and what their permission tier allows.

The role always comes from the session (set by the UI when the user signs in), never from
chat or tool arguments. Keep TIERS in sync with docs/security/self-assessment.md.
"""

from __future__ import annotations

from copilot.schemas import CopilotModel, Id, Role

__all__ = ["CAPABILITY_TOOLS", "TIERS", "Actor", "Role", "has_role"]


class Actor(CopilotModel):
    """The signed-in user behind a request. Built by the caller from session context only."""

    user_id: Id
    role: Role
    business_id: Id
    session_id: Id


# What each tier can do (each tier includes the tiers above it in this list).
TIERS: dict[Role, list[str]] = {
    Role.VIEWER: ["Read-only: analysis, forecasts, alerts, financing comparisons"],
    Role.STAFF: [
        "Draft reminders",
        "Set personal alert rules",
        "Pre-fill applications",
        "Draft adjustments",
    ],
    Role.OWNER: [
        "Send reminders",
        "Schedule payments",
        "Submit financing applications",
        "Mark invoices paid",
        "Apply and undo adjustments",
        "Save and remove forecast assumptions",
    ],
}


# The tools that deliver each write capability above (read-only tools all belong to Viewer).
# tests/unit/test_registry.py checks each tool exists with exactly that tier as its min_role,
# and that docs/security/self-assessment.md lists the same tools per tier.
CAPABILITY_TOOLS: dict[str, tuple[str, ...]] = {
    "Draft reminders": ("draft_reminder",),
    "Set personal alert rules": ("set_cash_floor",),
    "Pre-fill applications": ("prefill_application",),
    "Send reminders": ("send_reminder",),
    "Schedule payments": ("schedule_payment",),
    "Submit financing applications": ("submit_application",),
    "Mark invoices paid": ("mark_invoice_paid",),
    "Draft adjustments": ("draft_adjustment",),
    "Apply and undo adjustments": ("apply_adjustment", "undo_adjustment"),
    "Save and remove forecast assumptions": ("save_assumption", "remove_assumption"),
}


def has_role(actor: Actor, min_role: Role) -> bool:
    return actor.role >= min_role
