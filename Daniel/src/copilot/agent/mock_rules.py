"""RuleBasedLLM: a keyword-driven stand-in for a real model, so the demo runs without an API key.

It is not AI. It recognises a few requests, calls tools in a fixed order through the same
interface a real model uses, and writes its answer only from tool results (it formats numbers
but never calculates them). Anything it doesn't recognise gets a short help message.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from copilot.agent.llm import LLMResponse, Message, ToolCall
from copilot.dates import add_months
from copilot.schemas import sgd

HELP = (
    "I'm the rule-based demo assistant (no AI model connected yet). Try:\n"
    '- "How much cash do we have?"\n'
    '- "Will we run out of cash?" (13-week forecast)\n'
    '- "Any alerts?"\n'
    '- "What\'s coming up?" (bills, payroll and receipts in the next 4 weeks)\n'
    '- "Set my floor to S$50,000" (your own alert threshold)\n'
    '- "How did we do last quarter?"\n'
    '- "What\'s our DSO?" / "How dependent are we on our biggest customer?"\n'
    '- "Who pays late?" (unpaid invoices and bills by how overdue they are)\n'
    '- "Are we getting better or worse?" (monthly revenue, burn and trend)\n'
    '- "Can we afford our loan?" / "What\'s our break-even?"\n'
    '- "How did last month compare with the month before?" (what changed and why)\n'
    '- "Break down our expenses" (spending by category vs the month before)\n'
    '- "Where did our money go?" (money in and out by category, last 3 months)\n'
    '- "What if Bayfront pays 3 weeks late?" / "What if we hire someone at S$5,000 a month?"\n'
    '- "How do I fix the cash gap?" (options, and whether borrowing is needed)\n'
    '- "Pay bill BL-5048"\n'
    '- "Remind INV-1057" (saves a draft reminder), then "Send the reminder for INV-1057" (owner)\n'
    '- "Any unmatched receipts?" / "Mark INV-1064 paid" (owner, links a bank receipt)\n'
    '- "What are my financing options?" / "I need S$50k for 6 months"\n'
    '- "Prefill the top option" (staff/owner), then "Submit the application" (owner)'
)

_DOC_NUMBER = re.compile(r"\b([A-Za-z]{2,5}-\d{2,8})\b")
_TODAY = re.compile(r"Today is (\d{4}-\d{2}-\d{2})")
_UNTRUSTED = re.compile(r'</?untrusted(?: flagged="[^"]*")?>')
_AMOUNT = re.compile(r"S?\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?\b")
_OBLIGATIONS = re.compile(
    r"coming up|upcoming|obligation|calendar|due (this|next)|(have|need) to pay|what.{0,10}due"
)
_WHAT_IF = re.compile(r"\bwhat (if|happens if)\b")
_RECOMMEND = re.compile(
    r"\bfix\b|close the gap|what should (i|we) do|recommend|\bborrow|do (i|we) need (a )?loan"
)
_COMPARE = re.compile(
    r"\bcompare|\bvs\.?\b|versus|what changed|top movers|month on month|month over month"
    r"|why did .{0,30}\b(drop|fall|fell|rise|rose|go up|go down|increase|decrease)"
)
_EXPENSES = re.compile(r"expense|spending|\bspend\b|costs? by category|break ?down")
_WORKING = re.compile(
    r"\bdso\b|\bdpo\b|receivable days|days sales|working capital|cash conversion"
    r"|concentrat|(biggest|largest|top) (customer|supplier)|depend"
)
_AGEING = re.compile(
    r"\bage?ing\b|who owes|owes us|pays? late|paying late|slow pay|overdue (invoices|bills)"
    r"|receivables|payables"
)
_TREND = re.compile(
    r"\btrend|\bburn|better or worse|getting (better|worse)|improving|worsening|volatil"
    r"|how steady"
)
_HEALTH = re.compile(
    r"\bdscr\b|debt service|afford (our|the|this) loan|break[ -]?even"
    r"|what would a (bank|lender) think"
)
_STATEMENTS = re.compile(
    r"profit (and|&) loss|\bp ?& ?l\b|income statement|balance sheet|cash ?flow statement"
    r"|financial statements|net profit|really profitable|make a profit|own and owe"
)
_SUMMARY = re.compile(r"summary|inflows?\b|outflows?\b|where did .{0,15}money|money in and out")
_DURATION = re.compile(r"\b(\d{1,3})\s*(day|week|month)s?\b")
_FINANCING = re.compile(
    r"financ|loan options|which loan|compare (loans|lenders)|\blenders?\b|credit line"
    r"|\bi need (s\$|\$)?\d"
)
_PREFILL = re.compile(r"pre-?fill|apply for|start an application")
_SUBMIT = re.compile(r"\bsubmit\b")
_ORDINAL = {"second": 2, "third": 3, "fourth": 4}
_EDIT = re.compile(r"\baccru|\brelabel|recategori[sz]e|stock ?(count|take)")
_ASSUME = re.compile(r"\bassum|\bsave (that|this|it)\b.{0,20}(forecast|assum)")
_TXN_ID = re.compile(r"\b(t\d{5})\b", re.IGNORECASE)
_MONTHS = "january february march april may june july august september october november december"
_LINES = {
    "professional": "professional_fees",
    "accountant": "professional_fees",
    "legal": "professional_fees",
    "rent": "rent",
    "utilit": "utilities",
    "software": "software",
    "marketing": "marketing",
}
_THOUSANDS = re.compile(r"\b(\d+(?:\.\d+)?)\s?k\b")
_ALERTS_SHOWN = 5
_OBLIGATIONS_SHOWN = 12


FLAG_NOTE = "[looks like an instruction; ignored] "


def unwrap(text: Any) -> str:
    """Display form of a wrapped untrusted value (the mock shows it as data, never obeys it).
    Values flagged as instruction-like are pointed out, as the system prompt asks a model to."""
    raw = str(text)
    note = FLAG_NOTE if raw.startswith('<untrusted flagged="instruction-like">') else ""
    return note + html.unescape(_UNTRUSTED.sub("", raw))


def _pct(value: Any) -> str:
    return "n/a" if value is None else f"{Decimal(str(value)):.1%}"


class RuleBasedLLM:
    name = "Mock LLM (rules, no AI)"

    def complete(
        self, system: str, messages: list[Message], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        last_user = max(i for i, m in enumerate(messages) if m.role == "user")
        request = messages[last_user].content
        results: dict[str, dict] = {}
        for m in messages[last_user + 1 :]:
            if m.role == "tool":
                payload = json.loads(m.content)
                results[payload["tool"]] = payload
        failed = next((r for r in results.values() if not r["ok"]), None)
        if failed is not None:
            return _say(_explain_failure(failed))

        match = _TODAY.search(system)
        today = date.fromisoformat(match.group(1)) if match else date.today()
        allowed = {t["name"] for t in tools}
        text = request.lower()
        number = _DOC_NUMBER.search(request)

        if re.search(r"\bfloor\b", text) and re.search(r"\b(set|change|make|update)\b", text):
            return self._set_floor(request, results, allowed)
        if _WHAT_IF.search(text):
            return self._what_if(text, number.group(1) if number else None, results, today)
        if re.search(r"\bundo\b.{0,40}adjust|\bundo (that|it|the last)\b", text):
            return self._undo(results, allowed)
        if _EDIT.search(text):
            return self._adjust(request, text, results, allowed, today)
        if _ASSUME.search(text):
            return self._assume(text, results, allowed)
        if re.search(r"adjustments|assumptions", text):
            return self._once("list_adjustments", {}, results, _adjustments_text)
        if _SUBMIT.search(text):
            return self._submit(results, allowed)
        if _PREFILL.search(text):
            return self._prefill(text, results, allowed)
        if _HEALTH.search(text):
            return self._once("get_health_ratios", {}, results, _health_text)
        if _STATEMENTS.search(text):
            return self._once(
                "get_financial_statements", _statement_args(text), results, _statements_text
            )
        if _FINANCING.search(text):
            return self._once("find_financing", _need_args(text), results, _financing_text)
        if _RECOMMEND.search(text):
            return self._once("recommend_actions", {}, results, _recommend_text)
        if _COMPARE.search(text):
            return self._once("compare_periods", _last_full(text, today), results, _compare_text)
        if _WORKING.search(text):
            args = _last_full("quarter", today)
            return self._once("get_metrics", args, results, _working_text)
        if _AGEING.search(text):
            return self._once("get_ageing", {}, results, _ageing_text)
        if _TREND.search(text):
            return self._once("get_cash_trend", {}, results, _trend_text)
        if _EXPENSES.search(text):
            args = _last_full(text, today)
            return self._once("get_expense_breakdown", args, results, _expense_text)
        if _SUMMARY.search(text):
            end = date(today.year, today.month, 1) - timedelta(days=1)
            start = add_months(end + timedelta(days=1), -3)
            args = {"start": start.isoformat(), "end": end.isoformat(), "granularity": "month"}
            return self._once("get_cash_summary", args, results, _summary_text)
        if _OBLIGATIONS.search(text):
            return self._once("get_obligations", {}, results, _obligations_text)
        if re.search(r"\bmark\b.{0,40}\bpaid\b", text):
            return self._mark_paid(number.group(1) if number else None, results, allowed)
        if re.search(r"unmatched|unlinked|haven'?t matched|receipts", text):
            return self._once("list_receipts", {}, results, _receipts_text)
        if re.search(r"\bsend\b.{0,30}\bremind", text):
            return self._send_reminder(number.group(1) if number else None, results, allowed)
        if re.search(r"\bpay\b", text):
            return self._pay(number.group(1) if number else None, results, allowed, today)
        if "remind" in text:
            return self._remind(number.group(1) if number else None, results, allowed)
        if re.search(r"forecast|run out|next (few )?(weeks|months)|low point", text):
            return self._once("forecast_balance", {}, results, _forecast_text)
        if re.search(r"alert|worry|warning|risk", text):
            return self._once("get_alerts", {}, results, _alerts_text)
        if re.search(r"revenue|margin|how did we do|profit|performance|quarter", text):
            end = date(today.year, today.month, 1) - timedelta(days=1)
            start = add_months(end + timedelta(days=1), -3)
            args = {"start": start.isoformat(), "end": end.isoformat()}
            return self._once("get_metrics", args, results, _metrics_text)
        if re.search(r"cash|balance|bank|money", text):
            return self._once("get_cash_position", {}, results, _cash_text)
        return _say(HELP)

    # --- intents ---------------------------------------------------------------

    @staticmethod
    def _once(tool: str, args: dict, results: dict, render) -> LLMResponse:
        if tool not in results:
            return _call(tool, args)
        return _say(render(results[tool]["data"]))

    def _pay(self, number: str | None, results: dict, allowed: set, today: date) -> LLMResponse:
        if "schedule_payment" not in allowed:
            return _say("Only the business owner can make payments. You can ask them to do it.")
        if number is None:
            return _say('Which bill should I pay? Please give its number, e.g. "pay bill BL-5048".')
        if "list_bills" not in results:
            return _call("list_bills", {"status": "open"})
        bill = next(
            (
                b
                for b in results["list_bills"]["data"]
                if unwrap(b["number"]).lower() == number.lower()
            ),
            None,
        )
        if bill is None:
            return _say(f"I couldn't find an open bill numbered {number}.")
        supplier = unwrap(bill["counterparty_name"])
        if "list_payees" not in results:
            return _call("list_payees", {})
        payee = next(
            (
                p
                for p in results["list_payees"]["data"]
                if unwrap(p["name"]).casefold() == supplier.casefold()
            ),
            None,
        )
        if payee is None:
            return _say(f"There's no payee on file for {supplier}. Add and verify them first.")
        if "get_cash_position" not in results:
            return _call("get_cash_position", {})
        accounts = results["get_cash_position"]["data"]["value"]["accounts"]
        account = max(accounts, key=lambda a: Decimal(a["balance"]))
        if "schedule_payment" not in results:
            return _call(
                "schedule_payment",
                {
                    "payee_id": payee["id"],
                    "from_account_id": account["account_id"],
                    "amount": bill["outstanding"],
                    "pay_on": today.isoformat(),
                    "bill_id": bill["id"],
                },
            )
        return _say(
            f"I've prepared a payment of {sgd(bill['outstanding'])} for bill {number} "
            f"({supplier}). Please check the details shown and reply with the confirmation "
            "code if they are right."
        )

    def _what_if(self, text: str, number: str | None, results: dict, today: date) -> LLMResponse:
        if "run_what_if" in results:
            return _say(_what_if_text(results["run_what_if"]["data"]))
        days = _days(text)
        amount = _money(text)
        if number is not None or re.search(r"\blate|\bdelay|\bpush|on time", text):
            if "list_invoices" not in results:
                return _call("list_invoices", {"status": "open"})
            invoices = results["list_invoices"]["data"]
            invoice = next(
                (i for i in invoices if number and unwrap(i["number"]).lower() == number.lower()),
                None,
            )
            if invoice is not None:
                if "on time" in text:
                    change = {"kind": "collect_on_time", "invoice_id": invoice["id"]}
                elif days is None:
                    return _say(f"How many days late should I assume for {number}?")
                else:
                    change = {"kind": "delay_receipt", "invoice_id": invoice["id"], "days": days}
                return _call("run_what_if", {"changes": [change]})
            if number is not None:
                if "list_bills" not in results:
                    return _call("list_bills", {"status": "open"})
                bill = next(
                    (
                        b
                        for b in results["list_bills"]["data"]
                        if unwrap(b["number"]).lower() == number.lower()
                    ),
                    None,
                )
                if bill is None:
                    return _say(f"I couldn't find an open invoice or bill numbered {number}.")
                if days is None:
                    return _say(f"How many days later should {number} be paid?")
                change = {"kind": "delay_payment", "bill_id": bill["id"], "days": days}
                return _call("run_what_if", {"changes": [change]})
            customer = _customer_in(text, invoices)
            if customer is None:
                return _say(
                    'Which customer or invoice? For example: "what if Bayfront pays 3 weeks '
                    'late?" or "what if INV-1062 is 30 days late?"'
                )
            if days is None:
                return _say("How many days late should I assume?")
            change = {"kind": "delay_receipt", "customer_id": customer, "days": days}
            return _call("run_what_if", {"changes": [change]})
        if re.search(r"\bhire|new (staff|employee)", text):
            if amount is None:
                return _say("What would the new hire cost per month, including CPF?")
            start = add_months(date(today.year, today.month, 1), 1)
            change = {
                "kind": "add_monthly",
                "amount": f"-{amount}",
                "start": start.isoformat(),
                "label": "new hire",
            }
            return _call("run_what_if", {"changes": [change]})
        if re.search(r"\b(buy|spend|purchase)", text):
            if amount is None:
                return _say("How much would the purchase cost?")
            change = {
                "kind": "add_one_off",
                "amount": f"-{amount}",
                "date": (today + timedelta(days=7)).isoformat(),
                "label": "one-off purchase",
            }
            return _call("run_what_if", {"changes": [change]})
        return _say(
            "I can test: a customer or invoice paying late (or on time), a bill paid later, a "
            'one-off purchase, or a new hire. For example: "what if we hire someone at S$5,000 '
            'a month?"'
        )

    def _set_floor(self, request: str, results: dict, allowed: set) -> LLMResponse:
        if "set_cash_floor" not in allowed:
            return _say("Viewers can't change alert settings. Staff or the owner can.")
        if "set_cash_floor" in results:
            return _say(unwrap(results["set_cash_floor"]["message"]))
        match = _AMOUNT.search(request)
        if match is None:
            return _say('What floor should I set? For example: "set my floor to S$50,000".')
        floor = match.group(1).replace(",", "") + (match.group(2) or "")
        return _call("set_cash_floor", {"floor": floor})

    def _prefill(self, text: str, results: dict, allowed: set) -> LLMResponse:
        if "prefill_application" not in allowed:
            return _say("Viewers can't prepare applications. Staff or the owner can.")
        if "prefill_application" in results:
            return _say(_application_text(results["prefill_application"]["data"]))
        args = _need_args(text)
        if "find_financing" not in results:
            return _call("find_financing", args)
        ranked = results["find_financing"]["data"]["value"]["ranked"]
        if not ranked:
            return _say(_financing_text(results["find_financing"]["data"]))
        choice = _pick(text, ranked)
        if choice is None:
            return _say('I couldn\'t tell which option you mean. Say e.g. "prefill option 2".')
        return _call("prefill_application", {**args, "product_id": choice["quote"]["product_id"]})

    def _submit(self, results: dict, allowed: set) -> LLMResponse:
        if "submit_application" not in allowed:
            return _say("Only the business owner can submit a financing application.")
        if "submit_application" in results:
            return _say(
                "I've prepared the submission. Please check the details shown and reply with "
                "the confirmation code if they are right. Approval is the lender's decision."
            )
        if "list_applications" not in results:
            return _call("list_applications", {})
        drafts = [a for a in results["list_applications"]["data"] if a["status"] == "draft"]
        if not drafts:
            return _say('There is no draft application. Say "prefill the top option" first.')
        return _call("submit_application", {"application_id": drafts[-1]["id"]})

    def _open_invoice(self, number: str, results: dict) -> dict | LLMResponse:
        if "list_invoices" not in results:
            return _call("list_invoices", {"status": "open"})
        invoice = next(
            (
                i
                for i in results["list_invoices"]["data"]
                if unwrap(i["number"]).lower() == number.lower()
            ),
            None,
        )
        if invoice is None:
            return _say(f"I couldn't find an open invoice numbered {number}.")
        return invoice

    def _send_reminder(self, number: str | None, results: dict, allowed: set) -> LLMResponse:
        if "send_reminder" not in allowed:
            return _say("Only the owner can send reminders. Staff can save a draft for them.")
        if number is None:
            return _say("Which invoice's reminder should I send? Please give its number.")
        invoice = self._open_invoice(number, results)
        if isinstance(invoice, LLMResponse):
            return invoice
        if "list_reminders" not in results:
            return _call("list_reminders", {})
        drafts = [
            r
            for r in results["list_reminders"]["data"]
            if r["invoice_id"] == invoice["id"] and r["status"] == "draft"
        ]
        if not drafts and "draft_reminder" not in results:
            return _call("draft_reminder", {"invoice_id": invoice["id"]})
        draft_id = drafts[-1]["id"] if drafts else results["draft_reminder"]["data"]["id"]
        if "send_reminder" not in results:
            return _call("send_reminder", {"reminder_id": draft_id})
        return _say(
            f"The reminder for {number} goes only to the customer on that invoice. Please check "
            "the details shown and reply with the confirmation code if they are right."
        )

    def _mark_paid(self, number: str | None, results: dict, allowed: set) -> LLMResponse:
        if "mark_invoice_paid" not in allowed:
            return _say("Only the owner can mark invoices paid.")
        if number is None:
            return _say("Which invoice has been paid? Please give its number.")
        invoice = self._open_invoice(number, results)
        if isinstance(invoice, LLMResponse):
            return invoice
        if "list_receipts" not in results:
            return _call("list_receipts", {})
        fits = [
            r
            for r in results["list_receipts"]["data"]
            if r["customer_id"] == invoice["counterparty_id"]
            and Decimal(r["amount"]) <= Decimal(invoice["outstanding"])
        ]
        if not fits:
            return _say(
                f"I can't see a receipt from {unwrap(invoice['counterparty_name'])} that could "
                f"pay {number}, so I can't mark it paid. Nothing was changed."
            )
        if len(fits) > 1:
            lines = [f"- {r['date']}: {sgd(r['amount'])} ({r['transaction_id']})" for r in fits]
            return _say(f"Which receipt paid {number}?\n" + "\n".join(lines))
        if "mark_invoice_paid" not in results:
            args = {"invoice_id": invoice["id"], "transaction_id": fits[0]["transaction_id"]}
            return _call("mark_invoice_paid", args)
        return _say(
            f"I've prepared recording that receipt against {number}. No money moves. Please "
            "check the details shown and reply with the confirmation code if they are right."
        )

    def _adjust(
        self, request: str, text: str, results: dict, allowed: set, today: date
    ) -> LLMResponse:
        if "draft_adjustment" not in allowed:
            return _say("Viewers can't record adjustments. Staff draft them; the owner applies.")
        if "draft_adjustment" not in results:
            if "accru" in text:
                line = next((v for k, v in _LINES.items() if k in text), "other")
                args = {
                    "kind": "accrued_cost",
                    "month": _month_in(text, today),
                    "amount": _sgd_amount(request),
                    "line": line,
                }
            elif "stock" in text:
                args = {
                    "kind": "stock_count",
                    "month": _month_in(text, today),
                    "amount": _sgd_amount(request),
                }
            else:
                txn = _TXN_ID.search(request)
                if txn is None:
                    return _say("Which payment should I relabel? Please give its id (e.g. t00158).")
                personal = re.search(r"owner|drawing|personal|myself", text)
                to = (
                    "owner_draw"
                    if personal
                    else next((v for k, v in _LINES.items() if k in text), None)
                )
                args = {"kind": "relabel", "transaction_id": txn.group(1).lower(), "to": to}
            args = {k: v for k, v in args.items() if v is not None}
            return _call("draft_adjustment", {**args, "reason": request.strip()[:200]})
        saved = results["draft_adjustment"]
        if "apply_adjustment" not in allowed:
            return _say(
                unwrap(saved["message"])
                + " Only the owner can apply it, so ask them to review the draft."
            )
        if "apply_adjustment" not in results:
            return _call("apply_adjustment", {"adjustment_id": saved["data"]["adjustment_id"]})
        return _say(
            "I've prepared the adjustment. It moves no money and keeps the imported figures. "
            "Please check the effect shown and reply with the confirmation code if it's right."
        )

    def _undo(self, results: dict, allowed: set) -> LLMResponse:
        if "undo_adjustment" not in allowed:
            return _say("Only the owner can undo an adjustment.")
        if "list_adjustments" not in results:
            return _call("list_adjustments", {})
        applied = [
            a
            for a in results["list_adjustments"]["data"]["adjustments"]
            if a["status"] == "applied"
        ]
        if not applied:
            return _say("There is no applied adjustment to undo.")
        if "undo_adjustment" not in results:
            return _call("undo_adjustment", {"adjustment_id": applied[-1]["id"]})
        return _say(
            "I've prepared undoing it. Please check the effect shown and reply with the "
            "confirmation code if it's right."
        )

    def _assume(self, text: str, results: dict, allowed: set) -> LLMResponse:
        if "save_assumption" not in allowed:
            return _say(
                "Only the owner can save a forecast assumption. You can try it without saving: "
                'ask "what if ..." instead.'
            )
        if "save_assumption" in results:
            return _say(
                "I've prepared saving that assumption. It changes everyone's forecast until "
                "removed. Please check the effect shown and reply with the confirmation code."
            )
        if "list_invoices" not in results:
            return _call("list_invoices", {})
        customer = _customer_in(text, results["list_invoices"]["data"])
        days = re.search(r"\b(\d{1,3})\s*days?\b", text)
        if customer is None or days is None:
            return _say(
                'Which customer, and how many days after the due date? E.g. "assume Bayfront '
                'pays 43 days after the due date".'
            )
        args = {
            "kind": "payment_delay",
            "customer_id": customer,
            "days": int(days.group(1)),
            "reason": text[:200],
        }
        return _call("save_assumption", args)

    def _remind(self, number: str | None, results: dict, allowed: set) -> LLMResponse:
        if "draft_reminder" not in allowed:
            return _say("Viewers can't draft reminders. Staff or the owner can.")
        if number is None:
            return _say("Which invoice is the reminder for? Please give its number.")
        if "list_invoices" not in results:
            return _call("list_invoices", {"status": "open"})
        invoice = next(
            (
                i
                for i in results["list_invoices"]["data"]
                if unwrap(i["number"]).lower() == number.lower()
            ),
            None,
        )
        if invoice is None:
            return _say(f"I couldn't find an open invoice numbered {number}.")
        if "draft_reminder" not in results:
            return _call("draft_reminder", {"invoice_id": invoice["id"]})
        draft = results["draft_reminder"]["data"]
        return _say(f"Draft saved (not sent):\n\n{unwrap(draft['body'])}")


def _month_in(text: str, today: date) -> str | None:
    """'september 2026' / 'september' / '2026-09' -> '2026-09' (a month name without a year is
    the latest such month up to today)."""
    iso = re.search(r"\b(\d{4})-(0[1-9]|1[0-2])\b", text)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}"
    for n, name in enumerate(_MONTHS.split(), start=1):
        if re.search(rf"\b{name[:3]}(?:{name[3:]})?\b", text):
            year = re.search(r"\b(20\d{2})\b", text)
            y = int(year.group(1)) if year else today.year - (1 if n > today.month else 0)
            return f"{y}-{n:02d}"
    return None


def _adjustments_text(data: dict) -> str:
    lines = [f"- {a['id']} ({a['status']}): {a['description']}" for a in data["adjustments"]]
    for a in data["saved_assumptions"]:
        who = unwrap(a["customer"]) if a["customer"] else a["category"]
        if a["days"] is not None:
            what = f"pays {a['days']} days after the due date"
        else:
            what = f"{sgd(a['monthly_amount'])} a month from {a['start']}"
        lines.append(f"- assumption {a['id']} ({a['status']}): {who} {what}")
    months = data["open_months"]
    head = (
        f"Months open for adjustments: {', '.join(months)}."
        if isinstance(months, list)
        else "No months can be adjusted."
    )
    return head + ("\n" + "\n".join(lines) if lines else "\nNo adjustments or assumptions yet.")


def _days(text: str) -> int | None:
    match = _DURATION.search(text)
    if match is None:
        return None
    n, unit = int(match.group(1)), match.group(2)
    return n * {"day": 1, "week": 7, "month": 30}[unit]


def _money(text: str) -> str | None:
    """The largest amount of at least S$100 in the text, as a plain string (parsing only)."""
    found = [Decimal(m.group(1)) * 1000 for m in _THOUSANDS.finditer(text)]
    found += [
        Decimal(m.group(1).replace(",", "") + (m.group(2) or "")) for m in _AMOUNT.finditer(text)
    ]
    found = [f for f in found if f >= 100]
    return f"{max(found):.2f}" if found else None


_SGD_AMOUNT = re.compile(r"S\$\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?")


def _sgd_amount(text: str) -> str | None:
    """The first amount written with S$ (so a year like 2026 is never read as money)."""
    match = _SGD_AMOUNT.search(text)
    if match is None:
        return None
    return f"{Decimal(match.group(1).replace(',', '') + (match.group(2) or '')):.2f}"


def _need_args(text: str) -> dict:
    """Amount and months the user stated, if any (parsing only)."""
    args: dict = {}
    amount = _money(text)
    if amount is not None:
        args["amount"] = amount
    days = _days(text)
    if days is not None:
        args["months"] = max(1, -(-days // 30))  # rounded up
    return args


def _pick(text: str, ranked: list[dict]) -> dict | None:
    """Which ranked option the user means: 'option 2', 'second', a product word, or the top."""
    match = re.search(r"(?:option|#|number)\s*(\d)", text)
    if match:
        n = int(match.group(1))
        return ranked[n - 1] if 1 <= n <= len(ranked) else None
    for word, n in _ORDINAL.items():
        if word in text:
            return ranked[n - 1] if n <= len(ranked) else None
    names = {
        r["quote"]["product_id"]: set(re.findall(r"[a-z]{5,}", r["quote"]["product_name"].lower()))
        for r in ranked
    }
    for r in ranked:  # only words that name exactly one product ("invoice", not "financing")
        others = set().union(*(w for pid, w in names.items() if pid != r["quote"]["product_id"]))
        if any(re.search(rf"\b{w}\b", text) for w in names[r["quote"]["product_id"]] - others):
            return r
    return ranked[0]


def _customer_in(text: str, invoices: list[dict]) -> str | None:
    """Customer whose name's first word appears in the text, from the open-invoice list."""
    for inv in invoices:
        first = unwrap(inv["counterparty_name"]).split()[0].lower()
        if len(first) >= 4 and re.search(rf"\b{re.escape(first)}\b", text):
            return inv["counterparty_id"]
    return None


# --- rendering tool results -------------------------------------------------------


def _last_full(text: str, today: date) -> dict:
    """The last full calendar month (or 3 months if the user says quarter) before today."""
    end = date(today.year, today.month, 1) - timedelta(days=1)
    months = 3 if "quarter" in text else 1
    start = add_months(end + timedelta(days=1), -months)
    return {"start": start.isoformat(), "end": end.isoformat()}


def _day_count(value: Any) -> str:
    return "n/a" if value is None else f"{value} days"


def _notes(warnings: list[str]) -> list[str]:
    return [f"Note: {w}" for w in warnings]


def _cash_text(data: dict) -> str:
    value = data["value"]
    parts = ", ".join(f"{unwrap(a['name'])} {sgd(a['balance'])}" for a in value["accounts"])
    return f"You have {sgd(value['total'])} in total as of {value['as_of']}: {parts}."


def _drivers(drivers: list[dict], limit: int = 3) -> str:
    lines = [f"- {unwrap(d['label'])}: {sgd(d['amount'])}" for d in drivers[:limit]]
    return "\n".join(lines)


def _forecast_text(data: dict) -> str:
    value = data["value"]
    low = value["low_point"]
    first = next((w for w in value["weeks"] if Decimal(w["min_balance"]) < 0), None)
    if first is None:
        text = (
            f"Cash stays above zero for the next 13 weeks. The lowest point is "
            f"{sgd(low['balance'])} on {low['date']} (week {low['week']})."
        )
    else:
        text = (
            f"Cash first goes below zero in week {first['week']} ({first['start']} to "
            f"{first['end']}), dipping to {sgd(first['min_balance'])}. The lowest point in the "
            f"13 weeks is {sgd(low['balance'])} on {low['date']} (week {low['week']})."
        )
    if data["drivers"]:
        text += f"\nBiggest items in week {low['week']}:\n" + _drivers(data["drivers"])
    if value.get("saved_assumptions"):
        text += "\nThis uses your saved assumptions: " + "; ".join(
            unwrap(a) for a in value["saved_assumptions"]
        )
        without = value.get("low_point_without_saved")
        if without:
            text += (
                f". From the imported data alone the lowest point would be "
                f"{sgd(without['balance'])} on {without['date']}."
            )
    for warning in data["warnings"]:
        text += f"\nNote: {warning}"
    return text


def _alerts_text(data: dict) -> str:
    alerts = data["alerts"]["value"]
    floor = f"{sgd(data['floor'])} ({data['floor_source']})"
    if not alerts:
        return f"No alerts: forecast cash stays above your floor of {floor}."
    lines = [f"{len(alerts)} alert(s), most important first (floor: {floor}):"]
    for alert in alerts[:_ALERTS_SHOWN]:
        lines.append(f"- {alert['severity'].upper()}: {unwrap(alert['message'])}")
    if len(alerts) > _ALERTS_SHOWN:
        lines.append(f"...and {len(alerts) - _ALERTS_SHOWN} more.")
    top = alerts[0]
    if top["drivers"]:
        lines.append(f"Behind the top alert:\n{_drivers(top['drivers'])}")
    return "\n".join(lines)


def _obligations_text(data: dict) -> str:
    value = data["value"]
    items = value["items"]
    if not items:
        return f"Nothing known is due between {value['start']} and {value['end']}."
    lines = [
        f"Known money in and out from {value['start']} to {value['end']}: "
        f"{sgd(value['total_out'])} out, {sgd(value['total_in'])} in."
    ]
    for row in items[:_OBLIGATIONS_SHOWN]:
        lines.append(
            f"- {row['date']}: {unwrap(row['label'])}: {sgd(row['amount'])} "
            f"({row['certainty']}; balance after {sgd(row['balance_after'])})"
        )
    if len(items) > _OBLIGATIONS_SHOWN:
        lines.append(f"...and {len(items) - _OBLIGATIONS_SHOWN} more.")
    return "\n".join(lines)


def _metrics_text(data: dict) -> str:
    p = data["period"]["value"]
    r = data["runway"]["value"]
    runway = (
        "the business is cash-flow positive"
        if r["months"] is None
        else f"runway is about {r['months']} months at the recent burn rate"
    )
    text = (
        f"{p['start']} to {p['end']} (cash basis): revenue {sgd(p['revenue'])}, gross margin "
        f"{_pct(p['gross_margin'])}, operating margin {_pct(p['operating_margin'])}, net cash "
        f"flow {sgd(p['net_cash_flow'])}. Today {runway}."
    )
    w = data["working_capital"]["value"]
    largest = data["concentration"]["value"]["largest"]
    text += f"\nInvoice basis: DSO {_day_count(w['dso'])}, DPO {_day_count(w['dpo'])}"
    if largest is not None:
        text += (
            f"; largest customer {unwrap(largest['name'])} with {_pct(largest['share'])} of "
            "invoiced sales"
        )
    return text + "."


def _working_text(data: dict) -> str:
    w = data["working_capital"]["value"]
    c = data["concentration"]["value"]
    lines = [
        f"{w['start']} to {w['end']} (invoice basis):",
        f"- DSO {_day_count(w['dso'])}: {sgd(w['receivables'])} owed by customers at period "
        f"end, against {sgd(w['invoiced_sales'])} invoiced in the period.",
        f"- DPO {_day_count(w['dpo'])}: {sgd(w['payables'])} owed to suppliers at period end, "
        f"against {sgd(w['bills_received'])} of bills received.",
        f"- Cash conversion cycle {_day_count(w['ccc'])} (DSO minus DPO).",
    ]
    if w["net_working_capital"] is not None:
        lines.append(
            f"- Net working capital {sgd(w['net_working_capital'])}: cash {sgd(w['cash'])} plus "
            "receivables, minus payables."
        )
    if c["largest"] is not None:
        top = ", ".join(f"{unwrap(x['name'])} {_pct(x['share'])}" for x in c["customers"][:3])
        lines.append(f"- Share of invoiced sales: {top}.")
    suppliers = data["supplier_concentration"]["value"]["suppliers"]
    if suppliers:
        top = ", ".join(f"{unwrap(x['name'])} {_pct(x['share'])}" for x in suppliers[:3])
        lines.append(f"- Share of supplier bills: {top}.")
    drivers = data["working_capital"]["drivers"]
    unpaid = [d for d in drivers if unwrap(d["label"]).startswith("Unpaid")]
    if unpaid:
        lines.append("Largest unpaid invoices at period end:")
        lines += [
            f"- {unwrap(d['label'])}: {sgd(d['amount'])} ({unwrap(d['detail'])})" for d in unpaid
        ]
    warnings = data["working_capital"]["warnings"][1:] + data["concentration"]["warnings"][1:]
    return "\n".join(lines + _notes(warnings))


_AGEING_SIDES = (
    ("receivables", "Customers owe you", "invoices"),
    ("payables", "You owe suppliers", "bills"),
)


def _ageing_text(data: dict) -> str:
    lines = []
    for key, owed, noun in _AGEING_SIDES:
        v = data[key]["value"]
        if not v["buckets"] or all(b["count"] == 0 for b in v["buckets"]):
            lines.append(f"No unpaid {noun} as of {v['as_of']}.")
            continue
        lines.append(
            f"{owed} {sgd(v['total'])} as of {v['as_of']} (invoice basis); {sgd(v['overdue'])} "
            f"of it is overdue ({_pct(v['overdue_share'])})."
        )
        lines += [
            f"- {b['label']}: {sgd(b['amount'])} ({b['count']})" for b in v["buckets"] if b["count"]
        ]
        lines += [
            f"- Oldest overdue: {unwrap(d['number'])} from {unwrap(d['counterparty_name'])}, "
            f"{sgd(d['outstanding'])}, {d['days_overdue']} days overdue."
            for d in v["oldest_overdue"]
        ]
        if v["customers"]:
            habits = ", ".join(
                f"{unwrap(h['name'])} {h['avg_days_late']} days" for h in v["customers"][:3]
            )
            lines.append(f"Average days paid after the due date, slowest first: {habits}.")
    return "\n".join(lines)


def _statement_args(text: str) -> dict:
    if re.search(r"12 months|past year|last year|whole year|annual", text):
        period = "last_12_months"
    elif re.search(r"year to date|\bytd\b|this year", text):
        period = "ytd"
    elif "quarter" in text:
        period = "quarter"
    else:
        period = "month"
    statement = "all"
    if "balance sheet" in text or "own and owe" in text:
        statement = "balance_sheet"
    elif re.search(r"cash ?flow statement", text):
        statement = "cash_flow"
    elif re.search(r"profit (and|&) loss|\bp ?& ?l\b|income statement", text):
        statement = "pnl"
    return {"period": period, "statement": statement}


def _statements_text(data: dict) -> str:
    v = data["value"]
    if v is None:
        return data["warnings"][0]
    lines = [f"Financial statements for {v['period']} (accrual basis, excluding GST):"]
    if v["pnl"]:
        p, r = v["pnl"], v["ratios"]
        lines.append(
            f"- Profit and loss: revenue {sgd(p['revenue'])}, cost of sales "
            f"{sgd(p['cost_of_sales'])}, gross profit {sgd(p['gross_profit'])} "
            f"({_pct(r['gross_margin'])}), operating expenses "
            f"{sgd(p['total_operating_expenses'])}, operating profit "
            f"{sgd(p['operating_profit'])} ({_pct(r['operating_margin'])}), interest "
            f"{sgd(p['interest'])}, net profit {sgd(p['net_profit'])}."
        )
    if v["balance_sheet"]:
        b = v["balance_sheet"]
        lines.append(
            f"- Balance sheet at {b['as_of']}: assets {sgd(b['total_assets'])} (cash "
            f"{sgd(b['cash'])}, receivables {sgd(b['receivables'])}), liabilities "
            f"{sgd(b['total_liabilities'])}, equity {sgd(b['total_equity'])}."
        )
    if v["cash_flow"]:
        c = v["cash_flow"]
        lines.append(
            f"- Cash flow: operating {sgd(c['operating'])}, financing {sgd(c['financing'])}, "
            f"cash from {sgd(c['opening_cash'])} to {sgd(c['closing_cash'])}."
        )
    adj = v.get("adjustments")
    if adj:
        lines.append(
            f"- Includes {adj['count']} adjustment(s) by the owner: net profit as imported "
            f"{sgd(adj['net_profit_as_imported'])}, with adjustments "
            f"{sgd(adj['net_profit_with_adjustments'])}. "
            + " ".join(f"({a['description']})" for a in adj["applied"])
        )
    checks = v["checks"]
    lines.append(
        "- Checks: "
        + ("the balance sheet balances" if checks["balanced"] else "the balance sheet is OFF")
        + (
            "; closing cash matches the bank."
            if checks["cash_matches_bank"]
            else "; closing cash differs from the bank."
        )
    )
    return "\n".join(lines)


def _trend_text(data: dict) -> str:
    v = data["value"]
    lines = [
        f"Cash trend {v['start']} to {v['end']} (cash basis): {v['direction']}.",
        f"- Last 3 months, per month: revenue {sgd(v['avg_revenue_recent'])}, money out "
        f"{sgd(v['avg_burn_recent'])}, net {sgd(v['avg_net_recent'])}.",
    ]
    if v["avg_net_before"] is not None:
        lines.append(
            f"- The 3 months before: revenue {sgd(v['avg_revenue_before'])}, money out "
            f"{sgd(v['avg_burn_before'])}, net {sgd(v['avg_net_before'])}."
        )
    if Decimal(str(v["net_burn_recent"])) > 0:
        lines.append(f"- Net burn: {sgd(v['net_burn_recent'])} a month.")
    if v["revenue_volatility"] is not None:
        lines.append(
            f"- Revenue volatility {_pct(v['revenue_volatility'])} (how much monthly sales "
            "swing around their average)."
        )
    lines += [
        f"- {m['month']}: revenue {sgd(m['revenue'])}, out {sgd(m['gross_burn'])}, "
        f"net {sgd(m['net'])}"
        for m in v["months"][-3:]
    ]
    return "\n".join(lines + _notes(data["warnings"][1:]))


def _health_text(data: dict) -> str:
    d = data["debt_service_cover"]["value"]
    b = data["break_even"]["value"]
    if d["dscr"] is None:
        lines = [f"Debt service cover: no loan repayments between {d['start']} and {d['end']}."]
    else:
        lines = [
            f"Debt service cover {d['dscr']}x ({d['start']} to {d['end']}, cash basis): "
            f"{sgd(d['cash_available'])} left after running the business, against "
            f"{sgd(d['debt_service'])} of loan repayments."
        ]
    if b["break_even_monthly_sales"] is None:
        lines.append("Break-even sales can't be calculated: no positive gross margin recently.")
    else:
        lines.append(
            f"Break-even: about {sgd(b['break_even_monthly_sales'])} of sales a month covers "
            f"fixed costs of {sgd(b['avg_monthly_fixed_costs'])} at a "
            f"{_pct(b['gross_margin'])} gross margin; recent sales average "
            f"{sgd(b['avg_monthly_revenue'])} a month (headroom {sgd(b['headroom'])})."
        )
    notes = [f"Debt cover note: {w}" for w in data["debt_service_cover"]["warnings"][1:]]
    notes += [f"Break-even note: {w}" for w in data["break_even"]["warnings"][2:]]
    return "\n".join(lines + notes)


def _metric_line(m: dict) -> str:
    name = m["name"][0].upper() + m["name"][1:]
    if m["previous"] is None or m["current"] is None:
        before = "n/a" if m["previous"] is None else m["previous"]
        after = "n/a" if m["current"] is None else m["current"]
        return f"- {name} ({m['basis']} basis): {before} -> {after}"
    if m["unit"] == "sgd":
        change = _signed(m["change"])
        if m["pct_change"] is not None:
            change += f", {Decimal(str(m['pct_change'])):+.1%}"
        return (
            f"- {name} ({m['basis']} basis): {sgd(m['previous'])} -> {sgd(m['current'])} ({change})"
        )
    if m["unit"] == "ratio":
        points = f"{Decimal(str(m['change'])):+.1%}".replace("%", " pts")
        return (
            f"- {name} ({m['basis']} basis): {_pct(m['previous'])} -> {_pct(m['current'])} "
            f"({points})"
        )
    return (
        f"- {name} ({m['basis']} basis): {m['previous']} -> {m['current']} days "
        f"({Decimal(str(m['change'])):+} days)"
    )


_COMPARED = ("revenue", "net cash flow", "gross margin", "operating margin", "DSO", "DPO")
_MOVERS_SHOWN = 3


def _compare_text(data: dict) -> str:
    c = data["comparison"]["value"]
    cur, prev = c["current"], c["previous"]
    lines = [f"{cur['start']} to {cur['end']} compared with {prev['start']} to {prev['end']}:"]
    lines += [_metric_line(m) for m in c["metrics"] if m["name"] in _COMPARED]
    movers = data["movers"]["value"]["movers"][:_MOVERS_SHOWN]
    if movers:
        lines.append("What moved most (cash basis):")
    for m in movers:
        lines.append(
            f"- {m['category'].replace('_', ' ')}: {m['effect']}, {sgd(m['previous'])} -> "
            f"{sgd(m['current'])} ({m['note']})"
        )
        for cause in m["causes"][:2]:
            lines.append(
                f"    - {unwrap(cause['label'])}: {_signed(cause['change'])} ({cause['note']})"
            )
    warnings = [
        w
        for w in data["comparison"]["warnings"]
        if not w.startswith(("Cash basis", "Invoice basis"))
    ]
    return "\n".join(lines + _notes(warnings))


_EXPENSE_LINES = 8


def _expense_text(data: dict) -> str:
    v = data["value"]
    cur, prev = v["current"], v["previous"]
    change = _signed(v["change"])
    if v["pct_change"] is not None:
        change += f", {Decimal(str(v['pct_change'])):+.1%}"
    lines = [
        f"Spending {cur['start']} to {cur['end']} (cash basis): {sgd(v['total'])}, vs "
        f"{sgd(v['previous_total'])} in {prev['start']} to {prev['end']} ({change})."
    ]
    for line in v["lines"][:_EXPENSE_LINES]:
        status = f" [{line['status']}]" if line["status"] else ""
        lines.append(
            f"- {line['category'].replace('_', ' ')} ({line['group'].replace('_', '-')}): "
            f"{sgd(line['amount'])}, {_pct(line['share'])} of spend, "
            f"{_signed(line['change'])} vs before{status}"
        )
    if len(v["lines"]) > _EXPENSE_LINES:
        lines.append(f"...and {len(v['lines']) - _EXPENSE_LINES} more.")
    return "\n".join(lines + _notes(data["warnings"][1:]))


def _summary_text(data: dict) -> str:
    value = data["value"]
    lines = [
        f"Money in and out, {value['start']} to {value['end']} (bank transactions, transfers "
        f"between your own accounts left out): {sgd(value['total_inflows'])} in, "
        f"{sgd(value['total_outflows'])} out, net {sgd(value['net'])}."
    ]
    for p in value["periods"]:
        outs = [c for c in p["by_category"] if Decimal(c["amount"]) < 0][:3]
        top = ", ".join(f"{c['category'].replace('_', ' ')} {sgd(c['amount'])}" for c in outs)
        lines.append(
            f"- {p['start']} to {p['end']}: in {sgd(p['inflows'])}, out {sgd(p['outflows'])}, "
            f"net {sgd(p['net'])}" + (f" (biggest out: {top})" if top else "")
        )
    for warning in data["warnings"]:
        lines.append(f"Note: {warning}")
    return "\n".join(lines)


def _signed(amount: Any) -> str:
    return ("+" if Decimal(str(amount)) > 0 else "") + sgd(amount)


def _gap(g: dict) -> str:
    span = g["start"] if g["start"] == g["end"] else f"{g['start']} to {g['end']}"
    return f"{span} (down to {sgd(g['lowest_balance'])})"


def _what_if_text(data: dict) -> str:
    v = data["value"]
    lines = ["What-if (nothing has been changed for real):"]
    lines += [f"- {unwrap(n)}" for n in v["notes"]]

    # 1. The headline: what happens to the days below zero.
    before, after = v["base_first_below_zero"], v["scenario_first_below_zero"]
    for g in v["gaps_closed"]:
        lines.append(f"This closes the gap below zero from {_gap(g)}.")
    new = v["gaps_new"]
    if len(new) == 1:
        lines.append(f"This creates a new gap below zero from {_gap(new[0])}.")
    elif new:
        lines.append(
            f"This creates {len(new)} new gaps below zero: " + "; ".join(_gap(g) for g in new) + "."
        )
    for c in v["gaps_changed"]:
        was = "; ".join(_gap(g) for g in c["before"])
        lines.append(
            f"{'Worse' if c['worse'] else 'Better'}: cash is below zero from {_gap(c['after'])}, "
            f"instead of {was}."
        )
    if before is None and after is None:
        lines.append("Cash stays above zero for all 13 weeks either way.")
    elif after is None:
        lines.append("Cash now stays above zero for all 13 weeks.")
    elif before is None or after < before:
        lines.append(
            f"Cash now goes below zero on {after}"
            + (f", earlier than {before}." if before else ", which it otherwise wouldn't.")
        )
    elif after > before:
        lines.append(f"Cash now first goes below zero on {after} instead of {before}.")
    else:
        lines.append(f"Cash still first goes below zero on {before}.")

    # 2. Timing change or real change in money.
    if v["timing_only"]:
        lines.append(
            "This only changes timing: the same money moves, so the balance at the end of "
            f"the 13 weeks is unchanged ({sgd(v['scenario_end_balance'])})."
        )
    else:
        lines.append(
            f"Balance at the end of the 13 weeks: {sgd(v['base_end_balance'])} now, "
            f"{sgd(v['scenario_end_balance'])} in this scenario."
        )

    # 3. Which weeks differ, grouped.
    runs = v["week_runs"]
    if runs:
        lines.append("Difference by week (end-of-week balance vs now):")
        for r in runs[:4]:
            weeks = (
                f"Week {r['first_week']}"
                if r["first_week"] == r["last_week"]
                else f"Weeks {r['first_week']}-{r['last_week']}"
            )
            lines.append(f"- {weeks} ({r['start']} to {r['end']}): {_signed(r['difference'])}")
        if len(runs) > 4:
            lines.append(f"- ...and {len(runs) - 4} more changes later on.")
        if runs[-1]["last_week"] < 13:
            lines.append(f"From week {runs[-1]['last_week'] + 1} on: the same as now.")

    # 4. Overall low point last: it can sit outside the weeks that changed.
    base_low, low = v["base_low"], v["scenario_low"]
    if base_low == low:
        lines.append(f"The overall low point is unchanged: {sgd(low['balance'])} on {low['date']}.")
    else:
        lines.append(
            f"Overall low point: {sgd(base_low['balance'])} on {base_low['date']} now, "
            f"{sgd(low['balance'])} on {low['date']} in this scenario "
            f"(change {_signed(v['low_point_change'])})."
        )
    return "\n".join(lines)


def _financing_text(data: dict) -> str:
    v = data["value"]
    lines = [unwrap(v["message"])]
    if v["ranked"]:
        lines.append("Options, best fit first:")
    for r in v["ranked"]:
        q = r["quote"]
        months = f"{q['term_months']} month" + ("s" if q["term_months"] != 1 else "")
        fit = (
            "keeps cash above zero in the forecast"
            if r["keeps_cash_above_target"]
            else "cash still dips below zero"
        )
        lines.append(
            f"{r['rank']}. {q['product_name']} ({q['lender']}): borrow {sgd(q['amount'])} for "
            f"{months}, total cost {sgd(q['total_cost'])}, EIR {q['eir_pct']}%; {fit}."
        )
        lines += [f"   - {flag}" for flag in q["flags"][:2]]
    ineligible = [e for e in v["eligibility"] if not e["eligible"]]
    if ineligible:
        lines.append("Not eligible:")
        lines += [f"- {e['product_name']}: {'; '.join(e['reasons'])}" for e in ineligible]
    for warning in data["warnings"]:
        lines.append(f"Note: {warning}")
    if v["ranked"]:
        lines.append("Lenders and terms are illustrative (fictional lenders).")
    return "\n".join(lines)


def _application_text(d: dict) -> str:
    months = f"{d['term_months']} month" + ("s" if d["term_months"] != 1 else "")
    docs = "\n".join(f"- {doc}" for doc in d["documents"])
    return (
        f"Draft application {d['id']} saved (not sent): {d['product_name']} from {d['lender']}, "
        f"borrow {sgd(d['amount'])} for {months} from {d['draw_date']}, total cost "
        f"{sgd(d['total_cost'])}, EIR {d['eir_pct']}.\nDocuments the lender will ask for:\n"
        f"{docs}\n{d['disclaimer']} The owner can submit it."
    )


def _recommend_text(data: dict) -> str:
    v = data["value"]
    lines = [unwrap(v["message"])]
    if v["options"]:
        lines.append("Options, most preferred first:")
    for o in v["options"]:
        closes = o["effect"]["closes"]
        effect = (
            "on its own, closes the gap starting " + ", ".join(closes)
            if closes
            else "on its own, doesn't close a gap"
        )
        mark = "in the plan" if o["in_plan"] else "not needed in the plan"
        lines.append(f"{o['rank']}. {unwrap(o['title'])}: {effect} ({mark}). {o['assumption']}")
    need = v["funding_need"]
    if need is not None:
        end = (
            "cash hasn't recovered by the end of the forecast, so at least "
            f"{need['duration_days']} days"
            if need["duration_is_lower_bound"]
            else f"repayable from {need['repay_date']} ({need['duration_days']} days)"
        )
        lines.append(
            f"Funding need: {sgd(need['amount'])} from {need['draw_date']}; {end}. Matching "
            "financing products (with full cost) is not available in this demo yet."
        )
    for warning in data["warnings"]:
        lines.append(f"Note: {warning}")
    return "\n".join(lines)


def _explain_failure(result: dict) -> str:
    reasons = {
        "denied": "You don't have permission for that",
        "blocked": "The policy checks blocked this",
        "invalid": "That request wasn't valid",
        "rejected": "The bank sandbox refused it",
        "error": "Something was missing",
    }
    lead = reasons.get(result["outcome"], "That didn't work")
    return f"{lead}: {unwrap(result['message'])}"


def _say(text: str) -> LLMResponse:
    return LLMResponse(text=text)


def _call(name: str, arguments: dict) -> LLMResponse:
    return LLMResponse(
        tool_calls=(ToolCall(id=f"call-{uuid4().hex[:8]}", name=name, arguments=arguments),)
    )


def _receipts_text(data: list) -> str:
    if not data:
        return "Every customer receipt in the bank is already matched to an invoice."
    lines = [
        f"- {r['date']}: {sgd(r['amount'])} from {unwrap(r['customer_name'])} "
        f"({unwrap(r['description'])})"
        for r in data
    ]
    return (
        "Money received but not yet matched to an invoice:\n"
        + "\n".join(lines)
        + '\nThe owner can record one with e.g. "Mark INV-1064 paid".'
    )
