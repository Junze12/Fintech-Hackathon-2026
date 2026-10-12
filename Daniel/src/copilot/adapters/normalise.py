"""Parse raw text cells from external files into values the schemas accept.

Each function returns None for a blank cell and raises ValueError with a short,
human-readable reason for anything it can't parse.
"""

from __future__ import annotations

import re
from datetime import date

_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_SG_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_MONEY = re.compile(r"-?\d+(\.\d+)?")


def blank(value: str | None) -> str | None:
    """Strip whitespace; return None for an empty cell."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def parse_money(value: str | None) -> str | None:
    """'S$1,234.50' -> '1234.50'. Returns a string so the Money type does the final check."""
    value = blank(value)
    if value is None:
        return None
    cleaned = value.replace("S$", "").replace("$", "").replace(",", "").replace(" ", "")
    if not _MONEY.fullmatch(cleaned):
        raise ValueError(f"not a money amount: {value!r}")
    return cleaned


def parse_date(value: str | None) -> date | None:
    """Accept ISO (2026-09-01) or Singapore day-first (01/09/2026). Nothing else."""
    value = blank(value)
    if value is None:
        return None
    if match := _ISO_DATE.fullmatch(value):
        year, month, day = (int(g) for g in match.groups())
    elif match := _SG_DATE.fullmatch(value):
        day, month, year = (int(g) for g in match.groups())
    else:
        raise ValueError(f"date must be YYYY-MM-DD or DD/MM/YYYY, got {value!r}")
    try:
        return date(year, month, day)
    except ValueError:
        raise ValueError(f"not a real date: {value!r}") from None


_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}


def parse_bool(value: str | None) -> bool | None:
    value = blank(value)
    if value is None:
        return None
    lowered = value.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ValueError(f"not a true/false value: {value!r}")
