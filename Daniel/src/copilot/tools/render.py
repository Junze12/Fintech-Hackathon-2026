"""Turn tool results into what the LLM sees, with external text wrapped and labelled.

Every field typed UntrustedText (found with schemas.untrusted_fields) is wrapped as
<untrusted>...</untrusted> by copilot.untrusted, which escapes angle brackets inside it and
flags values that read like instructions. Account numbers are masked, money stays exact (as
text, not float).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, SecretStr

from copilot.schemas import mask, untrusted_fields
from copilot.untrusted import FLAGGED_OPEN_TAG, wrap_untrusted

__all__ = ["flagged_paths", "render_for_llm", "to_llm", "wrap_untrusted"]


def _wrap_all(value: Any) -> Any:
    """Wrap every string inside an untrusted field's value (str, list of str, dict values)."""
    if isinstance(value, str):
        return wrap_untrusted(value)
    if isinstance(value, list | tuple):
        return [_wrap_all(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _wrap_all(v) for k, v in value.items()}
    return to_llm(value)


def to_llm(value: Any) -> Any:
    """JSON-safe structure of value, with untrusted text wrapped and secrets masked."""
    if isinstance(value, BaseModel):
        untrusted = untrusted_fields(type(value))
        out = {}
        for name in type(value).model_fields:
            field_value = getattr(value, name)
            out[name] = _wrap_all(field_value) if name in untrusted else to_llm(field_value)
        return out
    if isinstance(value, SecretStr):
        return mask(value)
    if isinstance(value, Enum):
        return value.value if not isinstance(value.value, int) else value.name.lower()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [to_llm(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_llm(v) for k, v in value.items()}
    if value is None or isinstance(value, bool | int | str):
        return value
    raise TypeError(f"can't render {type(value).__name__} for the LLM")


def render_for_llm(value: Any) -> str:
    return json.dumps(to_llm(value), ensure_ascii=False)


def flagged_paths(rendered: Any, path: str = "") -> list[str]:
    """Where in a to_llm() result instruction-like text was flagged, e.g. "data[3].description"."""
    if isinstance(rendered, str):
        return [path or "value"] if rendered.startswith(FLAGGED_OPEN_TAG) else []
    if isinstance(rendered, dict):
        return [
            p
            for k, v in rendered.items()
            for p in flagged_paths(v, f"{path}.{k}" if path else str(k))
        ]
    if isinstance(rendered, list):
        return [p for i, v in enumerate(rendered) for p in flagged_paths(v, f"{path}[{i}]")]
    return []
