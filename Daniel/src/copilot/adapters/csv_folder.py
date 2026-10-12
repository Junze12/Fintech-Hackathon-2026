"""CSV adapter: one folder per business, one CSV file per entity.

Folder layout (headers equal the schema field names):
    business.csv        exactly one row (required)
    accounts.csv, counterparties.csv, payees.csv,
    transactions.csv, invoices.csv, bills.csv   (optional; missing -> warning)
    opening_balances.csv, inventory_snapshots.csv, fixed_assets.csv, loans.csv,
    loan_schedule.csv, payroll_runs.csv         (accrual inputs; optional, no warning)

business_id is taken from business.csv and never read from the other files, so a row
can't claim to belong to a different business.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from copilot.adapters.base import AdapterError
from copilot.adapters.normalise import blank, parse_bool, parse_date, parse_money
from copilot.schemas import (
    Account,
    Bill,
    Business,
    CopilotModel,
    Counterparty,
    FixedAsset,
    ImportResult,
    InventorySnapshot,
    Invoice,
    Loan,
    LoanInstalment,
    OpeningBalance,
    Payee,
    PayrollRun,
    RejectedRow,
    Transaction,
    balance_difference,
    mask,
)

_RAW_MAX = 500


@dataclass(frozen=True)
class _FileSpec:
    filename: str
    model: type[CopilotModel]
    money: frozenset[str] = frozenset()
    dates: frozenset[str] = frozenset()
    bools: frozenset[str] = frozenset()
    # field name -> name of the id set it must reference ("accounts" / "counterparties")
    refs: dict[str, str] = field(default_factory=dict)
    key: tuple[str, ...] = ("id",)  # fields that must be unique within the file
    optional: bool = False  # missing file is normal (accrual inputs): no warning


_BUSINESS = _FileSpec(
    "business.csv",
    Business,
    dates=frozenset({"incorporated_on"}),
    bools=frozenset({"registered_in_sg"}),
)

# Order matters: referenced entities load before the rows that reference them.
_SPECS: dict[str, _FileSpec] = {
    "accounts": _FileSpec(
        "accounts.csv",
        Account,
        money=frozenset({"opening_balance"}),
        dates=frozenset({"opening_date"}),
    ),
    "counterparties": _FileSpec("counterparties.csv", Counterparty),
    "payees": _FileSpec("payees.csv", Payee, bools=frozenset({"allowlisted", "verified"})),
    "transactions": _FileSpec(
        "transactions.csv",
        Transaction,
        money=frozenset({"amount"}),
        dates=frozenset({"date"}),
        refs={"account_id": "accounts", "counterparty_id": "counterparties"},
    ),
    "invoices": _FileSpec(
        "invoices.csv",
        Invoice,
        money=frozenset({"amount", "amount_paid", "gst"}),
        dates=frozenset({"issue_date", "due_date"}),
        refs={"counterparty_id": "counterparties"},
    ),
    "bills": _FileSpec(
        "bills.csv",
        Bill,
        money=frozenset({"amount", "amount_paid", "gst"}),
        dates=frozenset({"issue_date", "due_date"}),
        refs={"counterparty_id": "counterparties"},
    ),
    "opening_balances": _FileSpec(
        "opening_balances.csv",
        OpeningBalance,
        money=frozenset({"amount"}),
        dates=frozenset({"as_of"}),
        key=("line",),
        optional=True,
    ),
    "inventory_snapshots": _FileSpec(
        "inventory_snapshots.csv",
        InventorySnapshot,
        money=frozenset({"value"}),
        dates=frozenset({"date"}),
        key=("date",),
        optional=True,
    ),
    "fixed_assets": _FileSpec(
        "fixed_assets.csv",
        FixedAsset,
        money=frozenset({"cost", "residual_value"}),
        dates=frozenset({"acquired_on"}),
        optional=True,
    ),
    "loans": _FileSpec(
        "loans.csv",
        Loan,
        money=frozenset({"principal", "instalment"}),
        dates=frozenset({"start_date"}),
        optional=True,
    ),
    "loan_schedule": _FileSpec(
        "loan_schedule.csv",
        LoanInstalment,
        money=frozenset({"instalment", "interest", "principal", "balance_after"}),
        dates=frozenset({"due_date"}),
        refs={"loan_id": "loans"},
        key=("loan_id", "instalment_no"),
        optional=True,
    ),
    "payroll_runs": _FileSpec(
        "payroll_runs.csv",
        PayrollRun,
        money=frozenset({"gross_pay", "employee_cpf", "employer_cpf", "net_pay"}),
        dates=frozenset({"pay_date", "cpf_due_date"}),
        key=("period",),
        optional=True,
    ),
}


def _describe(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        where = ".".join(str(p) for p in item["loc"])
        message = item["msg"].removeprefix("Value error, ")
        parts.append(f"{where}: {message}" if where else message)
    return "; ".join(parts)


def _raw(row: dict[str | None, Any]) -> dict[str, str]:
    raw = {}
    for key, value in row.items():
        if key is None:
            continue
        text = value or ""
        if key == "account_number" and text:
            text = mask(text)
        raw[key] = text[:_RAW_MAX]
    return raw


def _check_opening(lines: list[OpeningBalance]) -> list[str]:
    """Whole-file checks a single row can't fail: one date, and the sheet balances."""
    if not lines:
        return []
    warnings = []
    dates = sorted({b.as_of for b in lines})
    if len(dates) > 1:
        warnings.append(
            "opening_balances.csv: rows have different as_of dates: "
            + ", ".join(d.isoformat() for d in dates)
        )
    difference = balance_difference(lines)
    if difference != 0:
        warnings.append(
            f"opening_balances.csv: assets minus liabilities and equity is {difference}, not 0"
        )
    return warnings


class CsvFolderAdapter:
    def load(self, path: Path) -> ImportResult:
        folder = Path(path)
        if not folder.is_dir():
            raise AdapterError(f"not a folder: {folder}")

        warnings: list[str] = []
        rejected: list[RejectedRow] = []
        business = self._load_business(folder)

        loaded: dict[str, list[Any]] = {}
        ids: dict[str, set[str]] = {}
        for name, spec in _SPECS.items():
            file = folder / spec.filename
            if not file.exists():
                if not spec.optional:
                    warnings.append(f"{spec.filename} not found; no {name} loaded")
                loaded[name], ids[name] = [], set()
                continue
            rows, row_rejects, file_warnings = self._load_file(file, spec, business.id, ids.get)
            loaded[name] = rows
            ids[name] = {r.id for r in rows} if "id" in spec.key else set()
            rejected.extend(row_rejects)
            warnings.extend(file_warnings)

        warnings.extend(_check_opening(loaded["opening_balances"]))
        return ImportResult(business=business, rejected=rejected, warnings=warnings, **loaded)

    def _load_business(self, folder: Path) -> Business:
        file = folder / _BUSINESS.filename
        if not file.exists():
            raise AdapterError(f"{_BUSINESS.filename} is required but missing in {folder}")
        with file.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 1:
            raise AdapterError(f"{_BUSINESS.filename} must have exactly one row, found {len(rows)}")
        values, errors = self._convert(rows[0], _BUSINESS)
        if errors:
            raise AdapterError(f"{_BUSINESS.filename}: " + "; ".join(errors))
        try:
            return Business(**values)
        except ValidationError as exc:
            raise AdapterError(f"{_BUSINESS.filename}: {_describe(exc)}") from None

    def _load_file(
        self,
        file: Path,
        spec: _FileSpec,
        business_id: str,
        id_set: Callable[[str], set[str] | None],
    ) -> tuple[list[Any], list[RejectedRow], list[str]]:
        allowed = set(spec.model.model_fields) - {"business_id"}
        rows: list[Any] = []
        rejected: list[RejectedRow] = []
        warnings: list[str] = []
        seen: set[tuple] = set()

        with file.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            header = set(reader.fieldnames or [])
            if "business_id" in header:
                warnings.append(
                    f"{spec.filename}: business_id column ignored (taken from business.csv)"
                )
            unknown = sorted(header - allowed - {"business_id"})
            if unknown:
                warnings.append(f"{spec.filename}: unknown column(s) ignored: {', '.join(unknown)}")

            for row in reader:
                line = reader.line_num

                def reject(reason: str, row: dict = row, line: int = line) -> None:
                    rejected.append(
                        RejectedRow(file=spec.filename, line=line, reason=reason, raw=_raw(row))
                    )

                if None in row:
                    reject("row has more cells than the header")
                    continue
                values, errors = self._convert(row, spec)
                if errors:
                    reject("; ".join(errors))
                    continue
                try:
                    record = spec.model(business_id=business_id, **values)
                except ValidationError as exc:
                    reject(_describe(exc))
                    continue
                key = tuple(getattr(record, k) for k in spec.key)
                if key in seen:
                    shown = key[0] if len(key) == 1 else key
                    reject(f"duplicate {'/'.join(spec.key)} {shown!r}")
                    continue
                missing = [
                    f"{field_name} {getattr(record, field_name)!r} not found in {target}"
                    for field_name, target in spec.refs.items()
                    if getattr(record, field_name) is not None
                    and getattr(record, field_name) not in (id_set(target) or set())
                ]
                if missing:
                    reject("; ".join(missing))
                    continue
                seen.add(key)
                rows.append(record)
        return rows, rejected, warnings

    @staticmethod
    def _convert(row: dict[str | None, Any], spec: _FileSpec) -> tuple[dict[str, Any], list[str]]:
        allowed = set(spec.model.model_fields) - (
            set() if spec.model is Business else {"business_id"}
        )
        values: dict[str, Any] = {}
        errors: list[str] = []
        for column, cell in row.items():
            if column is None or column not in allowed:
                continue
            try:
                if column in spec.money:
                    value = parse_money(cell)
                elif column in spec.dates:
                    value = parse_date(cell)
                elif column in spec.bools:
                    value = parse_bool(cell)
                else:
                    value = blank(cell)
            except ValueError as exc:
                errors.append(f"{column}: {exc}")
                continue
            if value is not None:
                values[column] = value
        return values, errors
