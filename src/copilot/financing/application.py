"""Financing application drafts: what a pre-filled application contains. Pure; no writes.

Only company facts go into an application (name, UEN, incorporation date, staff count, local
shareholding) plus the business's own 12-month figures and the quote. No personal data about
owners or staff. Saving the draft and submitting it are write tools (tools/write_tools.py),
both guarded and audited by policy/. Approval is always the lender's decision.
"""

from __future__ import annotations

from datetime import date, timedelta

from copilot.cashflow.recommend import FUNDING_PURPOSE, FundingNeed
from copilot.financing.costs import Quote
from copilot.financing.eligibility import Fact
from copilot.financing.ranking import DISCLAIMER
from copilot.schemas import (
    ApplicationStatus,
    Business,
    CopilotModel,
    FinancingApplication,
    Money,
    ProductType,
    UntrustedText,
)

_COMMON_DOCS = [
    "ACRA business profile (bizfile)",
    "Latest 6 months of business bank statements",
    "Latest financial statements or management accounts",
]
DOCUMENTS: dict[ProductType, list[str]] = {
    ProductType.INVOICE_FINANCING: [*_COMMON_DOCS, "Copies of the invoices to be financed"],
    ProductType.TRADE_FINANCING: [*_COMMON_DOCS, "Supplier invoices or purchase orders"],
}


class ApplicationDraft(CopilotModel):
    id: str
    status: ApplicationStatus
    lender: str
    product_id: str
    product_name: str
    purpose: UntrustedText
    need_amount: Money
    amount: Money
    term_months: int
    draw_date: date
    total_cost: Money
    eir_pct: str
    company: dict[str, UntrustedText]  # copied from the business's import file (R7)
    financials: list[Fact]
    documents: list[str]
    disclaimer: str


def need_for(app: FinancingApplication) -> FundingNeed:
    """The need an application was pre-filled for, to price it again at submission."""
    return FundingNeed(
        amount=app.need_amount,
        target=0,
        draw_date=app.draw_date,
        repay_date=app.draw_date + timedelta(days=app.need_days),
        duration_days=app.need_days,
        duration_months=app.need_months,
        duration_is_lower_bound=False,
        purpose=app.purpose or FUNDING_PURPOSE,
        basis="stated by the user",
    )


def build_draft(
    app: FinancingApplication, business: Business, quote: Quote, facts: list[Fact]
) -> ApplicationDraft:
    return ApplicationDraft(
        id=app.id,
        status=app.status,
        lender=quote.lender,
        product_id=quote.product_id,
        product_name=quote.product_name,
        purpose=app.purpose,
        need_amount=app.need_amount,
        amount=quote.amount,
        term_months=quote.term_months,
        draw_date=app.draw_date,
        total_cost=quote.total_cost,
        eir_pct=f"{quote.eir_pct}%",
        company={
            "name": business.name,
            "uen": business.uen,
            "industry": business.industry,
            "incorporated_on": business.incorporated_on.isoformat(),
            "employees": str(business.employee_count),
            "local_shareholding": f"{business.local_shareholding_pct.normalize():f}%",
        },
        financials=facts,
        documents=DOCUMENTS.get(quote.type, _COMMON_DOCS),
        disclaimer=DISCLAIMER,
    )
