"""The adapter interface: every external data format is converted through one of these."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from copilot.schemas import ImportResult


class AdapterError(Exception):
    """The input can't be imported at all (e.g. missing business record)."""


class Adapter(Protocol):
    def load(self, path: Path) -> ImportResult:
        """Read one business's data. Bad rows go into ImportResult.rejected, not exceptions."""
        ...
