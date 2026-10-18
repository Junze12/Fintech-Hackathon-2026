"""Bring your own data: the CSV files a business may upload on the sign-in page (known risk R54).

The browser sends each file's text; the server checks names and sizes here, writes the files to
a temporary folder and loads them through the same CSV adapter as the sample businesses. Only
the 14 entity files are accepted, so an upload can never plant the demo's scripted future
events or an answer key, and a name is never a path.
"""

from __future__ import annotations

from typing import Any

from copilot.runtime import DATA_FILES
from copilot.schemas import ImportResult

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_BODY_BYTES = 6 * 1024 * 1024  # JSON quoting adds a little to the 5 MB of files
MAX_REJECTED_SHOWN = 50

# What each file adds to the app (shown on the sign-in page and in the import summary).
UNLOCKS = {
    "business.csv": "the business's name and details",
    "accounts.csv": "bank accounts and today's cash",
    "counterparties.csv": "customers and suppliers by name",
    "payees.csv": "who payments may go to (allowlist)",
    "transactions.csv": "cash flow, forecast, trends and the stress test",
    "invoices.csv": "receivables, customer payment habits, overdue alerts",
    "bills.csv": "payables, upcoming bills in the forecast",
    "opening_balances.csv": "accrual statements, 3-year model and valuation",
    "inventory_snapshots.csv": "stock on the balance sheet and cost of sales",
    "fixed_assets.csv": "assets and depreciation",
    "loans.csv": "loans on the balance sheet",
    "loan_schedule.csv": "loan repayments in the forecast and debt service cover",
    "payroll_runs.csv": "payroll and CPF in the statements and model",
    "supplier_statements.csv": "checking bills against supplier statements",
}

FILES = list(DATA_FILES)
BUSINESS = "business.csv"


def columns(name: str) -> list[str]:
    """The file's headers: what the adapter reads, minus the fields the app sets itself."""
    return DATA_FILES[name][1]


def template_csv(name: str) -> str:
    return ",".join(columns(name)) + "\r\n"


def file_list() -> list[dict[str, Any]]:
    return [{"name": n, "required": n == BUSINESS, "unlocks": UNLOCKS[n]} for n in FILES]


def check(files: dict[str, str]) -> str | None:
    """A plain reason to refuse the whole upload, or None (the adapter strips a BOM)."""
    unknown = sorted(n for n in files if n not in FILES)
    if unknown:
        return (
            f"Unknown file name(s): {', '.join(unknown)}. Use the names from the list (no folders)."
        )
    if BUSINESS not in files:
        return "business.csv is required."
    sizes = {n: len(t.encode("utf-8")) for n, t in files.items()}
    big = [n for n, b in sizes.items() if b > MAX_FILE_BYTES]
    if big:
        return f"{big[0]} is larger than 2 MB."
    if sum(sizes.values()) > MAX_TOTAL_BYTES:
        return "The files together are larger than 5 MB."
    return None


def summary(result: ImportResult, provided: set[str]) -> dict[str, Any]:
    """Rows loaded and rejected per file, the files not provided, and the adapter's warnings.
    Rejected rows keep file, line and reason only (the raw row is untrusted text)."""
    rejected: dict[str, int] = {}
    for row in result.rejected:
        rejected[row.file] = rejected.get(row.file, 0) + 1
    loaded = {n: 1 if n == BUSINESS else len(getattr(result, DATA_FILES[n][0])) for n in provided}
    return {
        "files": [
            {"name": n, "loaded": loaded[n], "rejected": rejected.get(n, 0)}
            for n in FILES
            if n in provided
        ],
        "rejected_rows": [
            {"file": r.file, "line": r.line, "reason": r.reason}
            for r in result.rejected[:MAX_REJECTED_SHOWN]
        ],
        "rejected_total": len(result.rejected),
        "missing": [{"name": n, "unlocks": UNLOCKS[n]} for n in FILES if n not in provided],
        "warnings": result.warnings,
    }
