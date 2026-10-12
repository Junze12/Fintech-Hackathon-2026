"""Checks on the assistant's reply before the user sees it (data-extraction defence).

The system prompt and tool results are built so the model never holds a full account number or
a confirmation code, and is told not to reveal its instructions. This guard does not rely on
the model behaving; it runs plain code on every reply:
- a reply that contains the session's canary, or repeats two or more of the safety-rule lines
  verbatim, is replaced with a fixed refusal (the model was leaking its instructions);
- text that looks like a confirmation ("confirm 1234") is removed, so the model can't coach the
  user into confirming something it chose;
- links and images are removed ("![x](https://...)", bare web addresses): rendered as Markdown,
  an image loads its address with no click, so injected text could make the reply carry data
  out to an attacker's server; the assistant never needs a link;
- account-number-like digit runs are masked (••••1234). Amounts and dates are left alone.
Each intervention is returned as an event so the loop can audit it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from copilot.schemas import mask_account_like

REFUSAL = (
    "I can't share my instructions or internal details. I can help with this business's "
    "cash, invoices, bills, forecasts and financing."
)
CODE_REMOVED = "[code removed]"
LINK_REMOVED = "[link removed]"

_CONFIRM_LIKE = re.compile(r"\bconfirm\s*#?\s*\d{4}\b", re.IGNORECASE)
# A Markdown image or link with its target, or a bare web address.
_LINK = re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)|\b(?:https?://|www\.)\S+", re.IGNORECASE)
_MIN_RULE_CHARS = 40  # a rule line short enough to appear by chance doesn't count
_MAX_RULE_ECHOES = 1


@dataclass
class GuardedReply:
    text: str
    events: list[tuple[str, str]] = field(default_factory=list)  # (audit outcome, detail)


def _rule_lines(system_prompt: str) -> list[str]:
    return [
        line.strip()[2:].strip()
        for line in system_prompt.splitlines()
        if line.strip().startswith("- ") and len(line.strip()) >= _MIN_RULE_CHARS
    ]


def guard_reply(text: str, system_prompt: str, canary: str) -> GuardedReply:
    if not text:
        return GuardedReply(text)
    if canary and canary in text:
        return GuardedReply(REFUSAL, [("output_blocked", "reply contained the session canary")])
    echoed = sum(1 for rule in _rule_lines(system_prompt) if rule in text)
    if echoed > _MAX_RULE_ECHOES:
        return GuardedReply(
            REFUSAL, [("output_blocked", f"reply repeated {echoed} system-prompt rules")]
        )

    events: list[tuple[str, str]] = []
    cleaned = _CONFIRM_LIKE.sub(CODE_REMOVED, text)
    if cleaned != text:
        events.append(("redacted", "confirmation-code-like text removed"))
    unlinked = _LINK.sub(LINK_REMOVED, cleaned)
    if unlinked != cleaned:
        events.append(("redacted", "link or image removed"))
    masked = mask_account_like(unlinked)
    if masked != unlinked:
        events.append(("redacted", "account-number-like digits masked"))
    return GuardedReply(masked, events)
