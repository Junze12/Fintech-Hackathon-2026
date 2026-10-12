"""Shared data models: the contract every layer uses.

Conventions (see CLAUDE.md):
- Money is Decimal, never float, at most 2 decimal places (SGD cents).
- Sign convention for transactions: positive = money in, negative = money out.
- Business dates are local dates in UTC+8; timestamps must carry the UTC+8 offset.
- External free text is typed as UntrustedText so later layers can find and wrap it.
- Account numbers are secrets: they never appear in repr, logs or JSON dumps.
"""

from __future__ import annotations

import re
import typing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    model_validator,
)

SGT = timezone(timedelta(hours=8))


class CopilotModel(BaseModel):
    """Base for all models: immutable, and unknown fields are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Shared types -----------------------------------------------------------


def _reject_float(value: Any) -> Any:
    if isinstance(value, bool | float):
        raise ValueError("money must not be a float or bool; pass a str, int or Decimal")
    return value


def _check_cents(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("money must be a finite number")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValueError("money has at most 2 decimal places")
    return value


Money = Annotated[Decimal, BeforeValidator(_reject_float), AfterValidator(_check_cents)]
PositiveMoney = Annotated[Money, Field(gt=0)]
Currency = Literal["SGD"]
# Record ids are plain tokens, so an imported id can never carry a sentence to the model.
Id = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,64}$")]


class _UntrustedMarker:
    """Metadata marker: this field holds external free text (data, never instructions)."""

    def __repr__(self) -> str:
        return "UNTRUSTED"


UNTRUSTED = _UntrustedMarker()
UntrustedText = Annotated[str, StringConstraints(max_length=500), UNTRUSTED]


def _has_marker(annotation: Any) -> bool:
    if typing.get_origin(annotation) is Annotated:
        if any(m is UNTRUSTED for m in annotation.__metadata__):
            return True
    return any(_has_marker(arg) for arg in typing.get_args(annotation))


def untrusted_fields(model: type[BaseModel]) -> set[str]:
    """Names of the fields on `model` that hold untrusted external text."""
    return {
        name
        for name, field in model.model_fields.items()
        if any(m is UNTRUSTED for m in field.metadata) or _has_marker(field.annotation)
    }


_ACCOUNT_NUMBER = re.compile(r"[0-9-]{4,34}")


def _check_account_number(value: SecretStr) -> SecretStr:
    if not _ACCOUNT_NUMBER.fullmatch(value.get_secret_value()):
        raise ValueError("account number must be 4-34 digits or hyphens")
    return value


AccountNumber = Annotated[SecretStr, AfterValidator(_check_account_number)]


def mask(account_number: SecretStr | str) -> str:
    """Display form of an account number: '••••' plus the last 4 digits."""
    raw = (
        account_number.get_secret_value()
        if isinstance(account_number, SecretStr)
        else account_number
    )
    digits = re.sub(r"\D", "", raw)
    return "••••" + digits[-4:]


# A run of 8+ digits/hyphens that isn't part of a decimal number, an ISO date (2026-09-30) or
# a UEN (201812345D, digits then a letter): looks like an account number.
_ACCOUNT_LIKE = re.compile(
    r"(?<![\w-])(?<!\d\.)(?!\d{4}-\d{2}-\d{2}(?![\d-]))\d[\d-]{6,32}\d(?![\w-])(?!\.\d)"
)


def mask_account_like(text: str) -> str:
    """Mask every account-number-like run in free text (••••1234). Amounts are left alone."""
    return _ACCOUNT_LIKE.sub(lambda m: mask(m.group()), text)


def sgd(amount: Decimal | str | int) -> str:
    """Display form of an SGD amount: S$1,234.56, or -S$13,260.76 for negatives.

    The one money formatter for every message a user sees. Accepts str because tool results
    reach the agent as JSON text; floats are not accepted (money is never a float).
    """
    if isinstance(amount, float | bool):
        raise TypeError("money must not be a float or bool")
    value = Decimal(str(amount))
    return f"-S${-value:,.2f}" if value < 0 else f"S${value:,.2f}"


def _require_sgt(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(hours=8):
        raise ValueError("timestamps must be in UTC+8")
    return value


Timestamp = Annotated[AwareDatetime, AfterValidator(_require_sgt)]


# --- Enums ------------------------------------------------------------------


class CategoryGroup(StrEnum):
    REVENUE = "revenue"
    COGS = "cogs"
    OPEX = "opex"
    FINANCING = "financing"
    NON_OPERATING = "non_operating"
    UNCATEGORISED = "uncategorised"


class TransactionCategory(StrEnum):
    SALES = "sales"
    OTHER_INCOME = "other_income"
    FINANCING_INFLOW = "financing_inflow"
    COGS = "cogs"
    PAYROLL = "payroll"
    RENT = "rent"
    UTILITIES = "utilities"
    MARKETING = "marketing"
    SOFTWARE = "software"
    PROFESSIONAL_FEES = "professional_fees"
    TAX = "tax"
    LOAN_REPAYMENT = "loan_repayment"
    OWNER_DRAW = "owner_draw"
    TRANSFER = "transfer"
    OTHER = "other"
    UNCATEGORISED = "uncategorised"

    @property
    def group(self) -> CategoryGroup:
        return _CATEGORY_GROUPS[self]


_CATEGORY_GROUPS: dict[TransactionCategory, CategoryGroup] = {
    TransactionCategory.SALES: CategoryGroup.REVENUE,
    TransactionCategory.OTHER_INCOME: CategoryGroup.NON_OPERATING,
    TransactionCategory.FINANCING_INFLOW: CategoryGroup.FINANCING,
    TransactionCategory.COGS: CategoryGroup.COGS,
    TransactionCategory.PAYROLL: CategoryGroup.OPEX,
    TransactionCategory.RENT: CategoryGroup.OPEX,
    TransactionCategory.UTILITIES: CategoryGroup.OPEX,
    TransactionCategory.MARKETING: CategoryGroup.OPEX,
    TransactionCategory.SOFTWARE: CategoryGroup.OPEX,
    TransactionCategory.PROFESSIONAL_FEES: CategoryGroup.OPEX,
    TransactionCategory.TAX: CategoryGroup.NON_OPERATING,
    TransactionCategory.LOAN_REPAYMENT: CategoryGroup.FINANCING,
    TransactionCategory.OWNER_DRAW: CategoryGroup.NON_OPERATING,
    TransactionCategory.TRANSFER: CategoryGroup.NON_OPERATING,
    TransactionCategory.OTHER: CategoryGroup.OPEX,
    TransactionCategory.UNCATEGORISED: CategoryGroup.UNCATEGORISED,
}


class TransactionSource(StrEnum):
    """Where a transaction came from: imported history, or executed in the sandbox bank."""

    IMPORTED = "imported"
    SANDBOX = "sandbox"


class CounterpartyKind(StrEnum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    BOTH = "both"


class DocumentStatus(StrEnum):
    """Status of an invoice or bill. 'Overdue' is derived from due_date, not stored."""

    OPEN = "open"
    PAID = "paid"
    VOID = "void"


class PaymentStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    SCHEDULED = "scheduled"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class Role(IntEnum):
    """Permission tier. Higher includes everything lower can do (see policy/roles.py).

    Lives here, in the bottom layer, so tools can declare the minimum role they need
    without importing the policy layer above them.
    """

    VIEWER = 1
    STAFF = 2
    OWNER = 3

    @property
    def label(self) -> str:
        return self.name.lower()


class ProductType(StrEnum):
    TERM_LOAN = "term_loan"
    WORKING_CAPITAL_LOAN = "working_capital_loan"
    INVOICE_FINANCING = "invoice_financing"
    TRADE_FINANCING = "trade_financing"
    REVOLVING_CREDIT = "revolving_credit"
    OVERDRAFT = "overdraft"


class RateType(StrEnum):
    FLAT = "flat"
    REDUCING_BALANCE = "reducing_balance"


class RepaymentStructure(StrEnum):
    AMORTISING = "amortising"
    INTEREST_ONLY_BULLET = "interest_only_bullet"
    REVOLVING = "revolving"
    ON_INVOICE_SETTLEMENT = "on_invoice_settlement"


class FeeKind(StrEnum):
    PROCESSING = "processing"
    ADMIN = "admin"
    EARLY_REPAYMENT = "early_repayment"
    OTHER = "other"


class EligibilityMetric(StrEnum):
    """Facts about the business that eligibility rules may check.

    Deliberately excludes any personal characteristic of owners or staff
    (nationality, gender, religion, age, ...). local_shareholding_pct is a property
    of the company's ownership structure, required by real Singapore SME schemes.
    """

    MONTHS_OPERATING = "months_operating"
    ANNUAL_REVENUE = "annual_revenue"
    EMPLOYEE_COUNT = "employee_count"
    LOCAL_SHAREHOLDING_PCT = "local_shareholding_pct"
    GROSS_MARGIN = "gross_margin"
    AVERAGE_MONTHLY_BALANCE = "average_monthly_balance"
    REGISTERED_IN_SG = "registered_in_sg"


class Operator(StrEnum):
    GE = ">="
    LE = "<="
    EQ = "=="


# --- Entities ---------------------------------------------------------------


class Business(CopilotModel):
    """A small business. Holds no personal data about its owners."""

    id: Id
    name: UntrustedText  # from the import file: shown to the LLM wrapped, like any import text
    uen: str = Field(description="Singapore Unique Entity Number")
    industry: str
    incorporated_on: date
    employee_count: int = Field(ge=0)
    local_shareholding_pct: Decimal = Field(ge=0, le=100)
    registered_in_sg: bool = True


class Account(CopilotModel):
    id: Id
    business_id: Id
    name: UntrustedText
    bank_name: UntrustedText
    account_number: AccountNumber
    currency: Currency = "SGD"
    opening_balance: Money
    opening_date: date


class Counterparty(CopilotModel):
    id: Id
    business_id: Id
    name: UntrustedText
    kind: CounterpartyKind
    payment_terms_days: int = Field(default=30, ge=0)
    default_category: TransactionCategory | None = None


class Transaction(CopilotModel):
    """A bank-statement line. amount is signed: positive = in, negative = out."""

    id: Id
    business_id: Id
    account_id: Id
    date: date
    amount: Money
    description: UntrustedText
    counterparty_id: Id | None = None
    category: TransactionCategory = TransactionCategory.UNCATEGORISED
    source: TransactionSource = TransactionSource.IMPORTED

    @model_validator(mode="after")
    def _non_zero(self) -> Transaction:
        if self.amount == 0:
            raise ValueError("transaction amount must be non-zero")
        return self


class _Document(CopilotModel):
    """Shared shape of invoices (receivables) and bills (payables)."""

    id: Id
    business_id: Id
    counterparty_id: Id
    number: UntrustedText  # supplied by the counterparty's paperwork / the import file
    issue_date: date
    due_date: date
    amount: PositiveMoney
    amount_paid: Money = Decimal("0")
    status: DocumentStatus = DocumentStatus.OPEN
    notes: UntrustedText | None = None
    # GST included in amount (amount is the GST-inclusive total); 0 if none is charged.
    gst: Money = Decimal("0")

    @model_validator(mode="after")
    def _consistent(self) -> _Document:
        if self.due_date < self.issue_date:
            raise ValueError("due_date must not be before issue_date")
        if not (0 <= self.amount_paid <= self.amount):
            raise ValueError("amount_paid must be between 0 and amount")
        if not (0 <= self.gst < self.amount):
            raise ValueError("gst must be at least 0 and less than amount")
        if self.status is DocumentStatus.PAID and self.amount_paid != self.amount:
            raise ValueError("a paid document must have amount_paid equal to amount")
        return self


class Invoice(_Document):
    """Money owed to the business by a customer."""


class Bill(_Document):
    """Money the business owes a supplier."""


class Payee(CopilotModel):
    id: Id
    business_id: Id
    name: UntrustedText
    account_number: AccountNumber
    bank_name: UntrustedText
    allowlisted: bool = False
    verified: bool = False
    details_changed_at: Timestamp | None = None


class ScheduledPayment(CopilotModel):
    id: Id
    business_id: Id
    payee_id: Id
    from_account_id: Id
    amount: PositiveMoney
    pay_on: date
    status: PaymentStatus = PaymentStatus.PENDING_CONFIRMATION
    bill_id: Id | None = None
    reference: UntrustedText | None = None
    created_at: Timestamp


class Fee(CopilotModel):
    """A financing fee: either a flat amount or a percentage of the principal."""

    kind: FeeKind
    flat: PositiveMoney | None = None
    pct: Decimal | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def _exactly_one(self) -> Fee:
        if (self.flat is None) == (self.pct is None):
            raise ValueError("a fee needs exactly one of flat or pct")
        return self


class EligibilityRule(CopilotModel):
    metric: EligibilityMetric
    operator: Operator
    threshold: bool | Decimal
    description: str

    @model_validator(mode="after")
    def _threshold_matches_metric(self) -> EligibilityRule:
        if self.metric is EligibilityMetric.REGISTERED_IN_SG:
            if not isinstance(self.threshold, bool) or self.operator is not Operator.EQ:
                raise ValueError("registered_in_sg rules must use == with a true/false threshold")
        elif isinstance(self.threshold, bool):
            raise ValueError(f"{self.metric} rules need a numeric threshold")
        return self


class FinancingProduct(CopilotModel):
    """A catalogue product. Not business-scoped."""

    id: Id
    lender: str
    name: str
    type: ProductType
    min_amount: PositiveMoney
    max_amount: PositiveMoney
    min_term_months: int = Field(ge=1)
    max_term_months: int = Field(ge=1)
    rate_type: RateType
    annual_rate_pct: Decimal = Field(ge=0, le=100)
    fees: list[Fee] = []
    repayment: RepaymentStructure
    eligibility_rules: list[EligibilityRule] = []
    typical_use: str
    # Invoice financing: the most it will advance, as a % of the business's open receivables.
    advance_rate_pct: Decimal | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def _ranges(self) -> FinancingProduct:
        if self.min_amount > self.max_amount:
            raise ValueError("min_amount must not exceed max_amount")
        if self.min_term_months > self.max_term_months:
            raise ValueError("min_term_months must not exceed max_term_months")
        return self


class ApplicationStatus(StrEnum):
    """Only two states exist on our side: approval is the lender's decision, never ours."""

    DRAFT = "draft"
    SUBMITTED = "submitted"


class FinancingApplication(CopilotModel):
    """A financing application: pre-filled by staff or owner, submitted by the owner."""

    id: Id
    business_id: Id
    product_id: Id
    need_amount: PositiveMoney  # what the business needs to receive
    amount: PositiveMoney  # what it borrows (grossed up for fees, at least the minimum)
    term_months: int = Field(ge=1)
    draw_date: date
    # How long the money is needed, as at pre-fill, so submission prices exactly the same need.
    need_days: int = Field(ge=1)
    need_months: int = Field(ge=1)
    purpose: UntrustedText  # typed by the user
    status: ApplicationStatus = ApplicationStatus.DRAFT
    created_by: str
    created_at: Timestamp
    submitted_by: str | None = None
    submitted_at: Timestamp | None = None


class Reminder(CopilotModel):
    """A payment reminder for a customer invoice: drafted by staff or owner, sent by the owner.

    It has no recipient field: a reminder can only go to the invoice's own customer.
    """

    id: Id
    business_id: Id
    invoice_id: Id
    tone: Literal["friendly", "firm"]
    body: Annotated[str, UNTRUSTED]  # contains the customer's name and invoice number
    status: Literal["draft", "sent"] = "draft"
    created_by: str
    created_at: Timestamp
    sent_by: str | None = None
    sent_on: date | None = None  # simulated date
    sent_at: Timestamp | None = None


# --- Recorded adjustments and saved assumptions (chunk 13) ------------------------

AdjustmentKind = Literal["accrued_cost", "relabel", "stock_count"]
AssumptionKind = Literal["payment_delay", "recurring_change"]


class Adjustment(CopilotModel):
    """An owner's correction to the accrual books, kept beside the imported data (never
    overwriting it). Non-cash: it changes which line money counts in or when a cost counts.

    accrued_cost: `amount` of cost `line` incurred in `month`, reversed the month after.
    relabel: bank payment `transaction_id` counts as `to_category` instead.
    stock_count: month-end stock of `month` is `amount` instead of the stocktake.
    """

    id: Id
    business_id: Id
    kind: AdjustmentKind
    month: str = Field(pattern=r"^\d{4}-\d{2}$")  # YYYY-MM the adjustment belongs to
    amount: Money | None = None  # accrued_cost, stock_count
    line: TransactionCategory | None = None  # accrued_cost: the operating-cost line
    transaction_id: Id | None = None  # relabel
    to_category: TransactionCategory | None = None  # relabel
    reason: UntrustedText  # typed by the user
    status: Literal["draft", "applied", "undone"] = "draft"
    created_by: str
    created_at: Timestamp
    applied_by: str | None = None
    applied_at: Timestamp | None = None
    undone_by: str | None = None
    undone_at: Timestamp | None = None


class ForecastAssumption(CopilotModel):
    """An owner's saved assumption for the 13-week forecast (kept until removed).

    payment_delay: customer `counterparty_id` pays `days` after the due date.
    recurring_change: the recurring `category` cost is `amount` a month from `start`.
    """

    id: Id
    business_id: Id
    kind: AssumptionKind
    counterparty_id: Id | None = None
    days: int | None = Field(default=None, ge=0, le=180)
    category: TransactionCategory | None = None
    amount: Money | None = None  # recurring_change: monthly cost, positive
    start: date | None = None
    reason: UntrustedText
    status: Literal["active", "removed"] = "active"
    created_by: str
    created_at: Timestamp
    removed_by: str | None = None
    removed_at: Timestamp | None = None


# --- Accrual inputs (chunk 11) ------------------------------------------------


class BalanceLine(StrEnum):
    """A line of the opening balance sheet. Amounts are positive; the section gives the side."""

    CASH = "cash"
    RECEIVABLES = "receivables"
    INVENTORY = "inventory"
    FIXED_ASSETS_COST = "fixed_assets_cost"
    ACCUMULATED_DEPRECIATION = "accumulated_depreciation"  # deducted from assets
    PAYABLES = "payables"
    GST_PAYABLE = "gst_payable"
    CPF_PAYABLE = "cpf_payable"
    LOANS = "loans"
    SHARE_CAPITAL = "share_capital"
    RETAINED_EARNINGS = "retained_earnings"  # may be negative

    @property
    def section(self) -> Literal["asset", "contra_asset", "liability", "equity"]:
        return _BALANCE_SECTIONS[self]


_BALANCE_SECTIONS: dict[BalanceLine, Literal["asset", "contra_asset", "liability", "equity"]] = {
    BalanceLine.CASH: "asset",
    BalanceLine.RECEIVABLES: "asset",
    BalanceLine.INVENTORY: "asset",
    BalanceLine.FIXED_ASSETS_COST: "asset",
    BalanceLine.ACCUMULATED_DEPRECIATION: "contra_asset",
    BalanceLine.PAYABLES: "liability",
    BalanceLine.GST_PAYABLE: "liability",
    BalanceLine.CPF_PAYABLE: "liability",
    BalanceLine.LOANS: "liability",
    BalanceLine.SHARE_CAPITAL: "equity",
    BalanceLine.RETAINED_EARNINGS: "equity",
}


def balance_difference(lines: list[OpeningBalance]) -> Decimal:
    """Assets − liabilities − equity for a set of opening lines (0 when it balances)."""
    sign = {"asset": 1, "contra_asset": -1, "liability": -1, "equity": -1}
    return sum((sign[b.line.section] * b.amount for b in lines), Decimal("0"))


class OpeningBalance(CopilotModel):
    """One line of the balance sheet at the start of the data (from the accountant)."""

    business_id: Id
    as_of: date
    line: BalanceLine
    amount: Money

    @model_validator(mode="after")
    def _sign(self) -> OpeningBalance:
        if self.amount < 0 and self.line is not BalanceLine.RETAINED_EARNINGS:
            raise ValueError(f"{self.line} must not be negative")
        return self


class InventorySnapshot(CopilotModel):
    """A stocktake: value of stock on hand, at cost, at the end of `date`."""

    business_id: Id
    date: date
    value: Annotated[Money, Field(ge=0)]


class FixedAsset(CopilotModel):
    """A fixed-asset register entry, depreciated straight line to its residual value."""

    id: Id
    business_id: Id
    name: UntrustedText
    acquired_on: date
    cost: PositiveMoney
    residual_value: Annotated[Money, Field(ge=0)] = Decimal("0")
    useful_life_months: int = Field(ge=1)

    @model_validator(mode="after")
    def _residual(self) -> FixedAsset:
        if self.residual_value > self.cost:
            raise ValueError("residual_value must not exceed cost")
        return self


class Loan(CopilotModel):
    """A term loan contract. Its repayments are in loan_schedule (the bank's schedule)."""

    id: Id
    business_id: Id
    lender: UntrustedText
    principal: PositiveMoney
    annual_rate_pct: Decimal = Field(ge=0, le=100)
    start_date: date
    term_months: int = Field(ge=1)
    instalment: PositiveMoney


class LoanInstalment(CopilotModel):
    """One row of a loan's repayment schedule: how an instalment splits."""

    business_id: Id
    loan_id: Id
    instalment_no: int = Field(ge=1)
    due_date: date
    instalment: PositiveMoney
    interest: Annotated[Money, Field(ge=0)]
    principal: Annotated[Money, Field(ge=0)]
    balance_after: Annotated[Money, Field(ge=0)]

    @model_validator(mode="after")
    def _split(self) -> LoanInstalment:
        if self.interest + self.principal != self.instalment:
            raise ValueError("interest + principal must equal instalment")
        return self


class PayrollRun(CopilotModel):
    """One month's payroll. CPF (employee + employer share) is paid by cpf_due_date."""

    business_id: Id
    period: Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]  # YYYY-MM
    gross_pay: PositiveMoney
    employee_cpf: Annotated[Money, Field(ge=0)]
    employer_cpf: Annotated[Money, Field(ge=0)]
    net_pay: PositiveMoney
    pay_date: date
    cpf_due_date: date

    @model_validator(mode="after")
    def _consistent(self) -> PayrollRun:
        if self.gross_pay != self.net_pay + self.employee_cpf:
            raise ValueError("gross_pay must equal net_pay + employee_cpf")
        return self


# --- Import results ---------------------------------------------------------


class RejectedRow(CopilotModel):
    """An input row that failed validation. Recorded, never silently dropped."""

    file: str
    line: int = Field(ge=1)
    reason: str
    raw: dict[str, UntrustedText] = {}


class ImportResult(CopilotModel):
    """Everything an adapter produced from one business's data."""

    business: Business
    accounts: list[Account] = []
    counterparties: list[Counterparty] = []
    payees: list[Payee] = []
    transactions: list[Transaction] = []
    invoices: list[Invoice] = []
    bills: list[Bill] = []
    opening_balances: list[OpeningBalance] = []
    inventory_snapshots: list[InventorySnapshot] = []
    fixed_assets: list[FixedAsset] = []
    loans: list[Loan] = []
    loan_schedule: list[LoanInstalment] = []
    payroll_runs: list[PayrollRun] = []
    rejected: list[RejectedRow] = []
    warnings: list[str] = []


# --- Domain result contract -------------------------------------------------


class DataCoverage(CopilotModel):
    """Which data a result was computed from."""

    period_start: date
    period_end: date
    record_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> DataCoverage:
        if self.period_end < self.period_start:
            raise ValueError("period_end must not be before period_start")
        return self


class Driver(CopilotModel):
    """Something that explains a result, e.g. 'Payroll up 12%'.

    label and detail are marked untrusted because some are built from external text
    (e.g. 'Bill BL-5048 to <supplier name>'), so they are wrapped before reaching the LLM.
    """

    label: UntrustedText
    amount: Money | None = None
    detail: UntrustedText = ""


T = TypeVar("T")


class DomainResult(CopilotModel, Generic[T]):
    """What every domain function returns: the value plus how it was derived."""

    value: T
    drivers: list[Driver] = []
    data_coverage: DataCoverage
    warnings: list[str] = []
