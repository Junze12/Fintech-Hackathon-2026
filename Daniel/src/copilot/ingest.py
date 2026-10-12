"""Bring one business's data into the store: adapter -> save -> categorise."""

from __future__ import annotations

from pathlib import Path

from copilot.adapters.base import Adapter
from copilot.adapters.csv_folder import CsvFolderAdapter
from copilot.categorize import CategorisationSummary, categorise
from copilot.schemas import CopilotModel, DomainResult, ImportResult
from copilot.store import Store


class IngestReport(CopilotModel):
    imported: ImportResult
    categorisation: DomainResult[CategorisationSummary]


def ingest_folder(store: Store, path: Path, adapter: Adapter | None = None) -> IngestReport:
    """Load a business folder, save it, and categorise its transactions."""
    imported = (adapter or CsvFolderAdapter()).load(Path(path))
    store.save_import(imported)
    return IngestReport(imported=imported, categorisation=categorise(store, imported.business.id))
