# Core algorithms

Each section describes one algorithm: what it does, how, and why it was designed that way.
Sections are added as the code is built.

## Transaction categorisation (`src/copilot/categorize.py`)

**Goal:** give every transaction a `TransactionCategory`, so margins and expense breakdowns can
be computed. Each category maps to a group (revenue / cogs / opex / financing / non_operating).

**Method:** deterministic rules, no LLM. Rules are applied in order and the first match wins:

| # | Rule | Example | Why it is in this position |
|---|---|---|---|
| 1 | Already categorised in the source data → keep | Accounting export with categories | Never overwrite information the user or their bookkeeper gave us |
| 2 | Counterparty has a `default_category` → use it | "Tanjong Properties" → rent | An explicit mapping (or a user correction) is the strongest signal we can compute |
| 3 | Keyword rule on the description **and** the money direction matches | `SALARY SEP` (out) → payroll | Bank descriptions are the main signal. The direction check stops "RENT REFUND" (money in) from being booked as rent expense |
| 4 | Counterparty kind + direction | customer pays in → sales; we pay a supplier → cogs | A generic fallback for linked invoice and bill payments |
| 5 | Otherwise `uncategorised` | `POS 88213` | We never guess. Unknown spend is reported as such, with a warning |

**Why rules and not the LLM:** CLAUDE.md rule 1 (the LLM never produces numbers) extends to the
inputs of numbers. Categories decide what counts as revenue or cost, so they must be
reproducible and testable. Rules are also immune to prompt injection: descriptions are untrusted
text and are only matched against fixed regexes.

**User corrections:** setting a counterparty's `default_category` (e.g. "Stratus Hosting is
software, not cost of sales") and re-running applies the correction to every past and future
transaction with that counterparty (rule 2).

**Measured performance** (synthetic data, seed 42):

| Scenario | Transactions | Coverage | Accuracy on categorised |
|---|---|---|---|
| cash_crunch | 206 | 95.1% | 100% |
| concentrated_b2b | 193 | 95.3% | 100% |

The uncategorised ~5% are the deliberately vague descriptions, which is correct behaviour. The 100%
accuracy is optimistic: the rules and the generator's description templates were written by the
same team. Real bank exports will contain descriptions no rule anticipates. Those fall through to
`uncategorised` rather than being mislabelled, and the warning tells the user how much is
unexplained.

## Customer payment delays (`src/copilot/reconcile.py`)

**Goal:** know how late each customer really pays, so the forecast can time their money
(CLAUDE.md: "timed by each customer's historical payment delay, not the due date").

**Method:** light matching. Each paid invoice, oldest first, is matched to the earliest unused
receipt from the same customer with **exactly the same amount**, dated on or after the issue date.
Delay = receipt date − due date (negative = early). Each customer's mean is used.

**Result on synthetic data:** every paid invoice matched, and every estimate equals the answer
key's observed mean (e.g. Bayfront 22.5 days late, Lumen 40.2).

**Limits:** two invoices with the same amount could be swapped (this only shifts delay estimates).
Partial and combined payments aren't matched. Unmatched invoices produce a warning above 10%. A
customer with no matches is assumed to pay on the due date, with a warning. Full reconciliation
is deferred.

**Settlement dates (chunk 4a).** The matching is shared as `match_settlements(kind)`, which also
matches bills to supplier payments (same supplier, same amount, money out). It returns the date
each paid document was settled. `outstanding_at(as_of)` then rebuilds receivables or payables at
any past date: a document issued on or before `as_of` counts until its settlement date. A paid
document with no match is assumed paid on its due date. For an open document with a part payment,
the paid part is assumed to have arrived before `as_of`. Both cases are listed and produce a
warning. Hand-checked in `test_analysis.py` (e.g. an August invoice paid on 2 Oct still counts
at 30 Sep).

## Metrics (`src/copilot/analysis/metrics.py`)

Cash basis in v1 (accrual deferred). Every result says so.

| Metric | Definition |
|---|---|
| Revenue | Sum of `revenue`-group transactions (sales received) |
| COGS / Opex | Minus the sum of the `cogs` / `opex` group (so costs are positive numbers) |
| Gross margin | (Revenue − COGS) / Revenue, 4 dp. `None` if no revenue |
| Operating margin | (Revenue − COGS − Opex) / Revenue |
| Net cash flow | All money in minus out, excluding own-account transfers |
| Runway | Cash ÷ average monthly net outflow over the last 3 months. Only when net outflow > 0, otherwise "cash-flow positive" |

Uncategorised transactions are excluded from revenue and costs, and counted in a warning.

**Insight from testing: runway hides timing.** cash_crunch burns only S$2,250 a month on average
(Jul +S$3.9k, Aug −S$74.6k, Sep +S$64.0k), so its runway is **68 months**. Yet the forecast shows
the account going negative on **5 Nov 2026, five weeks out**. Averages hide lumpy payments. This is
why the agent should lead with the forecast, not runway, when asked "am I okay on cash?".

### Working capital and concentration (chunk 4a, invoice basis)

| Metric | Definition (period of D days) |
|---|---|
| DSO | Receivables at period end ÷ invoices issued in the period × D (0.1 day) |
| DPO | Payables at period end ÷ supplier bills issued in the period × D |
| Cash conversion cycle | DSO − DPO. **DIO is omitted** (no inventory data), always with a warning |
| Customer concentration | Largest customer's invoiced sales ÷ all invoiced sales in the period. Warns above 50% |

`None` plus a reason when a denominator is zero. Drivers list receivables, payables and the three
largest unpaid invoices at period end.

**Why invoice basis:** receivables and payables only exist on invoices and bills. Dividing them by
cash receipts would mix two bases, and the textbook definitions use credit sales and purchases.
The concentration result matches the answer key exactly (Bayfront 60.9%, Tidewater 61.2% of
invoiced sales since 2025-10-01).

**Insight from testing: cash basis swings with payment timing.** In cash_crunch, August's cash
gross margin is **−13.9%** (July 54.0%) because Bayfront paid one invoice instead of two and
Orchid paid none. Nothing changed in the business itself. In the same month DSO rose from 37.2
to 51.5 days. The comparison shows both side by side, so the owner sees a collections problem,
not a margin collapse.

## Business health measures (`src/copilot/analysis/health.py`, chunk 8)

Added for owners and lenders. All pure functions returning `DomainResult`; every result names its
basis. "Whole months" means calendar months ending on or before today (today's month counts only
if today is its last day).

| Measure | Basis | Definition |
|---|---|---|
| Receivables / payables ageing | invoice | Unpaid part (amount − amount paid) of open invoices or bills at today, by days past due: not yet due, 1–30, 31–60, 61–90, over 90. Plus overdue share and the three oldest overdue documents |
| Payment habit (receivables) | invoice + bank | Each customer's mean days paid after the due date, from `reconcile.estimate_payment_delays` (the same matching the forecast uses), slowest first |
| Cash trend | cash | Last 12 whole months (3–12): revenue, gross burn (all money out excl. own transfers), net. Last-3 vs previous-3 month averages; net burn = −average net if negative; revenue volatility = population std dev ÷ mean of monthly revenue. Direction: improving / worsening if the change in average net exceeds 5% of average monthly burn, else steady; under 6 months = "not enough history" |
| Debt service cover (DSCR) | cash | Last 12 whole months: (all flows except own transfers, loan repayments, loan drawdowns and uncategorised receipts; incl. tax and owner drawings) ÷ loan repayments. `None` with a reason when there are no repayments |
| Break-even sales | cash | Last 3 whole months: average monthly operating expenses ÷ gross margin; headroom = average monthly sales − break-even. `None` when the margin is ≤ 0 |
| Net working capital | invoice + cash | Cash at period end + receivables − payables (`working_capital(..., sandbox=)`) |
| Supplier concentration | invoice | Largest supplier's bills ÷ all supplier bills issued in the period. Warns above 50% |

**Uncategorised payments count as operating costs** in DSCR and break-even. They are real money out
that no rule labelled; counting them lowers DSCR and raises break-even, so the error is on the safe
side. Uncategorised receipts are left out for the same reason. Each result says how many and how
much. Checked: the answer key's opex equals our opex plus uncategorised payments, every month, in
both scenarios.

**Not possible with this chunk's data:** current and quick ratio (no balance sheet), DIO (no
inventory), gearing and interest cover (repayments only, no loan balance or interest split),
accrual profit. Chunk 11 added the inputs for all of these (see "Accrual inputs" below); chunk 12
computes them.

**Ground truth:** the generator now records `receivables_ageing`, `payables_ageing` and `suppliers`
from its own documents; trend, DSCR and break-even are checked against `monthly_totals`. All match
exactly. cash_crunch: S$45,783.49 overdue (INV-1057), DSCR **0.61**, break-even S$124,480.60 a month
vs S$132,684.45 actual, net working capital S$183,849.78 at 30 Sep, Meridian 79.1% of supplier
bills. concentrated_b2b: no loan (DSCR n/a), trend improving (net S$4,647 → S$12,425 a month).
(DSCR was 1.46 before chunk 11. The GST payments were then a placeholder about 40% of what 9%
GST implies. With real returns, the cash left to repay the loan falls from S$73.6k to S$30.9k a year.)

**Insight for the deck:** cash_crunch's sales are above break-even (S$8.2k headroom a month), yet
DSCR is 0.61 and the forecast goes negative on 5 Nov. Break-even counts only operating costs, while
GST and loan repayments are real cash too. Averages also miss timing, which is why the copilot
leads with the forecast.

## Period comparison and top movers (`src/copilot/analysis/compare.py`, chunk 4a)

- **Comparison:** `period_metrics` and `working_capital` for both periods. Each metric gives
  previous, current, change (current − previous; points for ratios) and % change for S$ metrics.
  The % is `None` when the base is 0 **or the sign flips** (net cash flow +S$3.9k → −S$74.6k
  would otherwise read "−2022%"). Periods of different lengths get a warning, except whole
  calendar months of 30 vs 31 days.
- **Top movers:** all categories except transfers, ranked by the absolute change in signed cash
  flow (top 5). Each mover has an effect ("less money in", "more spending", …) and a note
  comparing transaction counts ("3 receipts vs 5", "only in the previous period"). Its **causes**
  are the counterparties whose amounts changed most in the mover's direction (top 3), each with
  the same kind of note. Money with no counterparty (rent, payroll, tax) is grouped as "No named
  counterparty". Example (cash_crunch, Aug vs Jul): sales −S$85,702.43, led by Bayfront
  (1 receipt vs 2) and Orchid (only in July); tax "only in the previous period" (quarterly GST).

## Expense breakdown (`src/copilot/analysis/breakdown.py`, chunk 4a)

Reuses `cash_summary` for both periods (no second grouping). Each category with net money out
gets its spend (positive), share of total spend, group (cogs / opex / financing /
non-operating), change and % change vs the comparison period. `new` / `stopped` flag
categories present in only one period. Totals match the answer key's monthly outflows exactly
(cash_crunch August S$132,572.75).

## Recurring costs (`src/copilot/cashflow/recurring.py`)

**Scope:** categorised outflows with no counterparty (rent, payroll, CPF, utilities, software,
loan, GST, bank charges). Customer and supplier flows are forecast from invoices and bills.

**Method:**
- Within each category, cluster transactions by day of month (a gap of more than 5 days starts a new cluster). This is how payroll on the 27th and CPF on the 14th become separate items.
- A cluster is **monthly** if seen in ≥5 of the last 6 months.
- It is **quarterly** if seen in ≥3 of the last 12 months, always in the same month-of-quarter.
- Amount = median of the last 3 months. Day = median day.

## 13-week forecast (`src/copilot/cashflow/forecast.py`)

**Weeks:** Monday to Sunday. Week 1 contains the day after `as_of`, and there are 13 weeks.
Start = total cash across all accounts.

**Items, most certain first:**
0. **Scheduled payments** the owner confirmed through the copilot, on their payment date. A
   payment against a bill reduces that bill's open item by the same amount, so nothing is
   counted twice (chunk 4b-1).
1. **Open bills:** paid on their due date (overdue bills: tomorrow).
2. **Open invoices:** due date + the customer's mean delay. If that has already passed: within 7 days.
3. **Future invoices and bills:** each customer's and supplier's last 6 months give invoices per month, typical issue days and the median amount. Receipts arrive at issue + terms + delay. We pay bills at issue + terms.
4. **Recurring fixed costs** (above).

With under 8 weeks of history, only 1–2 are used, with a warning. Every item is labelled with
its source. The drivers are the 5 largest items in the low-point week. The assumptions are listed
in plain English for the agent to show.

**How it's scored (agreed 2026-10-03).** The forecast estimates habits from noisy history, so a
payment can land a day or two from the true date. When that crosses a Sunday/Monday boundary, a
single week's balance jumps by the whole payment. Examples: B2B week 3 is +S$54k because the
S$66k Tidewater payment is expected on Saturday rather than Monday. Crunch week 13 is −S$52k because
history says Bayfront invoices on the 6th, not the 5th, so a payment falls a day past the window.
Scoring every single week would punish correct behaviour, so we score what users rely on:

| Check | cash_crunch | concentrated_b2b |
|---|---|---|
| First day below zero (±7 days) | **5 Nov, exact** | never (correct) |
| Lowest balance (within tolerance) | −S$13.0k vs −S$17.8k (tol S$21.0k) | S$156.1k vs S$155.5k |
| Average weekly error (≤ tolerance) | S$6.8k (tol S$21.0k) | S$8.7k (tol S$15.0k) |

(Re-measured 2026-10-10 after chunk 11 made GST payments real.)

**Known gap:** our forecast shows three similar dips for cash_crunch (weeks 6, 11, 13), where the
truth has one deep dip (week 6). So our *lowest* point is week 13, while the *first* breach (5 Nov)
is right. The alert leads with the first breach for this reason.

## Alerts (`src/copilot/cashflow/alerts.py`, chunk 4b-1)

**Default floor** = one month of recurring fixed costs (quarterly costs count ⅓): S$68,771 for
cash_crunch (answer key S$68,542) and S$74,381 for B2B. **Floor used:** a floor given for one
check > the user's saved floor (`set_cash_floor`, staff) > the default.

Three v1 alert types:

| Type | Fires when | Severity | SGD at stake (impact) | Date |
|---|---|---|---|---|
| threshold | any forecast day is below the floor | critical if the low point is below zero, else warning | lowest balance's gap below the floor | first breach |
| shortfall | a stretch of days below zero. Names the biggest payment due in it (scheduled payment, open/expected bill or recurring cost) | critical | how far below zero it goes | first day below zero |
| overdue receivable | an open invoice is past its due date | info if within the customer's usual delay + 7 days, else warning | outstanding amount | due date (urgent now) |

The threshold alert explains the breach where it starts (the 5 largest items that week). The
overdue alert compares with the customer's measured average delay (`reconcile.py`), so Bayfront's
INV-1057, 11 days late when Bayfront usually pays 22 days late, is "normal for them" (info).

**Ranking (agreed 2026-10-04).** Severity first (critical, warning, info), then
`score = impact × urgency`. Urgency is 1 within 7 days (or already overdue), then 7/days
(0.5 at two weeks, 0.25 at four). The first proposal multiplied by a severity weight in a single
score. On cash_crunch that put an info note ("INV-1057 is late, but that's normal for Bayfront",
score S$11.4k) above the S$85,000 bill the business can't pay (S$1.9k: S$9.6k short, 36 days
away), so severity now sorts first. Cash_crunch at 2026-09-30: floor breach → S$85k Meridian bill
on 5 Nov → two later dips (Dec 6, Dec 27) → INV-1057 (info).

**New alerts.** After the clock moves, `new_alerts(before, after)` returns alerts whose key is
new or whose severity went up. Keys are stable across small date shifts: `threshold`,
`shortfall:<payment label>`, `overdue:<invoice id>`. Example: +7 days from 2026-09-30 reports
INV-1061 (due 4 Oct) as newly overdue.

## Obligations calendar (`src/copilot/cashflow/obligations.py`, chunk 4b-1)

The next N weeks (default 4, max 13) of **known** items from the forecast: scheduled payments
("scheduled"), open bills on their due date ("due"), recurring costs and expected receipts on
open invoices ("estimated"). Projected future invoices and bills are left out of the list but
still count in each row's `balance_after`, which is the forecast's end-of-day balance. Nothing
is recalculated: amounts come from the forecast items.

## Cash-flow summaries (`src/copilot/cashflow/summary.py`, chunk 4b-2)

Money in and out of the bank accounts per calendar month or Mon–Sun week (clipped to the range),
split by category, plus net and totals. Built from **transactions** (cash basis, what actually
moved), not invoices. Transfers between the business's own accounts are left out. Uncategorised
flows stay in as their own line with a warning. Since 4a the sandbox categorises everything it
posts, so this line only holds what no rule could classify. Max 60 periods per request.

## What-if (`src/copilot/cashflow/scenarios.py`, chunk 4b-2)

A scenario is up to 5 changes applied to a copy of the forecast's items, then walked again with
`forecast.walk` and compared with the base, week by week:

| Change | Effect on the items |
|---|---|
| `collect_on_time {invoice_id}` | that invoice's receipt moves to its due date (already overdue: as-of + 7 days), never later than now expected |
| `delay_receipt {invoice_id or customer_id, days}` | one invoice, or every open and projected receipt from that customer, arrives N days later |
| `delay_payment {bill_id, days}` | an open bill is paid N days later |
| `add_one_off {amount, date, label}` | one extra item (− out, + in) inside the 13 weeks |
| `add_monthly {amount, start, label}` | a new monthly item from `start` (e.g. a new hire's total cost incl. CPF) |
| `pause_recurring {category, until}` | recurring items of that category are skipped up to `until` |

To find items, forecast items now carry `ref` (bill/invoice/scheduled-payment id or recurring
category) and `counterparty_id`, so nothing is matched by parsing labels. Ids are looked up
**within the session's business**. Unknown, other-business or already-paid ids are an error,
never a guess. An item pushed past the horizon drops out, with a note. Output: low point before
and after, first day below zero before and after, end balance, per-week difference
(scenario − base), the items that moved, and a note per change. Also, so that the answer can
lead with what matters (agreed 2026-10-05): the stretches below zero in each case and which were
**closed**, which are **new**, and which **changed** depth or length (`worse` flag); whether the
scenario is **timing only** (items moved but none added, dropped or paused, so the end balance
can't change); and **week runs**, consecutive weeks with the same difference ("weeks 4–6:
+S$51,283.20"). Why: when a payment only moves in time, the overall low point and end balance
often stay the same (cash_crunch's low is Dec 27, after any November change), and leading with
"change S$0.00" made a useful fix look useless.

cash_crunch examples (as of 2026-09-30): INV-1062 paid on time moves the first day below zero
from Nov 5 to Dec 6. Bayfront paying 3 weeks late takes the low point from −S$13,025.81 to
−S$70,660.41 (Nov 14). A S$5,000/month hire from Oct 1 lowers the end balance by S$15,000.

## Recommendations and the funding need (`src/copilot/cashflow/recommend.py`, chunk 4b-2)

**Target:** zero, plus an optional buffer (agreed 2026-10-05). The user's alert floor isn't
used here: borrowing to hold a one-month cushion would inflate the need about six-fold
(≈S$82k vs ≈S$13k on cash_crunch), and the floor varies by who is signed in.

1. **Gaps** = runs of days the forecast balance is below the target.
2. **Candidate options**, in CLAUDE.md's order of preference, each expressed as a what-if change:
   - *collect*: an open invoice expected after a gap starts that, if paid by its due date
     (overdue: within 7 days), would arrive before that gap ends. Follow-up tool: `draft_reminder`.
   - *reschedule*: an open bill not already scheduled through the copilot, due in a gap or up
     to 7 days before one, paid 14 days later (needs the supplier's agreement).
   - *cut*: recurring costs in discretionary categories (marketing, professional fees, owner
     draws) paused until the last gap ends. Software, utilities, rent, payroll, tax, loans and
     "other" (bank fees) are treated as fixed.
   Each option is scored **on its own** against the base case: low point, number of gaps,
   days below target and which gaps it closes completely.
3. **Plan:** options are applied cumulatively in that order. One is kept only if it reduces the
   shortfall area (S$ × days below target), and the plan stops when no gap is left. The overall
   low point alone would hide progress: on cash_crunch it is the last day (Dec 27) whatever
   happens in November.
4. **Funding need** (the 4c contract) from what is left after the plan: `amount` = deepest
   shortfall (a loan of that size drawn on the first day below target keeps every later day at
   or above it); `draw_date` = first day below target; `repay_date` = the day after the last
   day below target, i.e. from then on the balance without the loan stays above target to the
   horizon end. If cash is still below target on the last forecast day, `repay_date` is None,
   `duration_is_lower_bound` is True and a warning says so. `duration_months` is rounded up for
   matching loan terms. Interest and fees are not included: 4c prices them per product. The
   need with no action (`need_without_actions`) is returned too, for comparison.

**cash_crunch result (as of 2026-09-30).** Gaps: Nov 5–9 (−S$9,376.45), Dec 6–10
(−S$9,891.21), Dec 27 (−S$13,025.81). Option 1: chase INV-1062 (S$51,283.20, due Oct 19, now
expected Nov 10). It closes November and is in the plan. Option 2: delay MFI-88120 (S$85,000)
by 14 days. It would also close November on its own, but isn't needed once INV-1062 is
collected. December is **structural**: payroll plus the projected supplier bills outrun receipts,
and timing changes don't fix it. There is no discretionary spend to cut. Funding need:
S$13,025.81 from Dec 6, for at least 22 days (cash hasn't recovered by Dec 27). Without action:
the same amount from Nov 5. concentrated_b2b has no gap, so the answer is "no action needed,
borrowing not needed".

## Financing-option matching (`src/copilot/financing/`, chunk 4c)

**Catalogue** (`data/catalogue/products.json`, `catalogue.py`): seven illustrative products
from fictional lenders, modelled on common Singapore SME financing types (EFS-style working
capital, micro loan, unsecured term loan, invoice financing, revolving line, trade financing,
an alternative lender's short-term loan). Each is validated against `FinancingProduct`. Bad
entries are rejected with reasons (an unknown metric such as `owner_age` can't even be
written as a rule).

**Need** (`needs.py`): the forecast's funding need after the non-borrowing plan (4b-2), or the
user's stated amount and months. If the plan closes every gap and the user stated nothing,
there is no need, and the answer says borrowing isn't needed. If only one of amount or months
is given and the forecast can't supply the other, we ask.

**Eligibility** (`eligibility.py`): company facts only, each with its source. Months operating
(since incorporation), 12-month cash-basis revenue and gross margin (`period_metrics`),
employees, local shareholding, registration, and the average of six month-end balances.
Each rule passes, fails or is unknown with a plain reason ("employees: 14 staff; needs at most
10 staff"). **Unknown = not eligible.** Invoice financing is also capped at 80% of open invoices
no more than 90 days overdue.

**Cost** (`costs.py`), for the actual need:
- *Amount:* grossed up so that the cash left after upfront fees equals the need, and at least
  the product minimum (over-borrowing is flagged). *Term:* the need's months, clipped to the
  product's range (flagged both ways).
- *Dated cash flows:* reducing-balance annuity; flat rate (interest = amount × rate × years,
  equal instalments); interest-only bullet; revolving and invoice products pay interest only
  on the days drawn (at least 30).
- *Total cost* = interest + fees. *EIR* = XIRR of the dated flows (the annual rate at which
  they net to zero, by calendar days), by bisection in Decimal. Checked by hand: S$12k at 7.5%
  over 12 months → S$1,041.09/month and 7.79% (textbook 7.76% on equal months). A 5.5% *flat*
  rate → 10.51% effective.
- Early-repayment fees are disclosed, not priced in.

**Ranking** (`ranking.py`, agreed 2026-10-05): only eligible products that can lend enough.
Each one's draw and repayments are added to the forecast (with the non-borrowing plan) and
walked again. Order: **keeps cash at or above the target for 13 weeks** first, then **lowest
total S$ cost**, then (only if a month in the last six had negative net cash flow) more
flexible repayment (revolving > invoice > bullet > amortising). Repayments after the 13 weeks
can't be checked, which the answer says.

**cash_crunch result (as of 2026-09-30):** need S$13,025.81 from Dec 6 (after chasing
INV-1062). Eligible: 6 of 7 (the micro loan fails: 14 staff > 10). Ranked: trade financing
S$169.52 (EIR 16.44%), invoice financing S$183.82 (18.59%), revolving line S$605.61 (73.83%:
a S$500 fee on a one-month draw), short-term loan S$886.29 (48.58%), EFS-style loan
S$1,021.79 (9.82%, but S$20k minimum and 12-month term), term loan S$3,750.00 (14.77%). The
lowest EIR is not the lowest cost: a low rate on a bigger, longer loan than you need costs
more in dollars. concentrated_b2b: no gap → borrowing not needed.

**Applications** (`application.py` + write tools): a draft contains company facts and the
business's own figures only, the quote, a document checklist per product type, and the
disclaimer. Its need (amount, draw date, days, months) is stored, so submission re-prices the
exact same need.

## Scripted world and the simulated clock (`sandbox/world.py`, `policy/scheduler.py`, chunk 4b-1)

**Why.** Advancing the clock with nothing happening would skip rent, payroll and customer
receipts. The forecast would then quietly drop them as "in the past", look too optimistic, and
alerts would disappear when they should be getting worse.

**What.** The generator writes `world_events.csv` per scenario: the true next 13 weeks using
true means and no noise. It holds open invoices paid at due date + the customer's true delay
(already late: +7 days), open and future bills paid on their due date, future invoices and bills
issued on their usual days, fixed costs on their day, and the B2B reserve transfer. The forward
answer key in `ground_truth.json` is computed **from the same event list**, so the two can't
disagree. Regenerating changed no existing file: the answer key is byte-identical.

**Replay, per day:** new documents → receipts → transfers → debits and bill payments, then
the owner's scheduled payments for that day (guard re-checked). A supplier bill is skipped if
the owner is paying it through the copilot. A debit that would overdraw the account bounces,
and a bounced bill stays open (overdue).

**Checked against the answer key:** a hands-off replay of cash_crunch matches the total balance
at the end of weeks 1–5 to the cent. On 2026-11-05 the S$85,000 MFI-88120 payment bounces
(insufficient funds), so from week 6 the sandbox is exactly S$85,000 above the answer key, which
assumed it was paid. B2B matches all 13 weeks to the cent. After +7 days, our forecast still
first goes below zero on 2026-11-05.

## Synthetic data generation (`src/copilot/synthetic.py`)

**Goal:** realistic businesses with *known* correct answers, so metrics, forecasts and alerts can
be scored automatically.

**Method:**
1. **Truth first.** A scenario defines the business's real structure: customers (with invoice
   size, payment terms and true mean days-late), suppliers, recurring costs (rent, payroll, CPF,
   utilities, software, loan, quarterly GST) and one-off bills.
2. **Emit with noise.** Twelve months of history (2025-10-01 → 2026-09-30) are generated from that
   truth with random variation in amounts, issue days and payment delays. Description templates
   vary (`"SALARY SEP25"`, `"Payroll - September 2025"`). About 5% of transactions are
   deliberately vague.
3. **Warm start.** Invoices and bills are also simulated for the three months before the history,
   and only the payments that land inside the window are kept. Without this, the business would
   start with no receivables in flight and spend two months paying costs with no income, which
   is unrealistic.
4. **Ground truth is recorded from the truth model, not computed by the app**, so tests aren't
   circular. It holds:
   - the true category of every transaction
   - monthly totals
   - closing balances
   - customer shares and true payment delays
   - overdue invoices
   - recurring patterns
   - a forward truth
5. **Forward truth.** The expected balance path (total cash, all accounts) for the next 13
   Monday-to-Sunday weeks. It uses true means with no noise:
   - open invoices arrive at due date + the customer's true mean delay
   - open bills are paid on their due date
   - future invoices, bills and recurring costs follow the scenario's pattern

   A tolerance (15% of average monthly outflow) is recorded for scoring the forecast.
   Since 4b-1 the forward path is computed from the same event list that is written to
   `world_events.csv` for the sandbox to replay (see "Scripted world" above).
6. **Calibration** (cash_crunch only). The opening balance is solved so the forward low point
   lands near a target (−S$18,000). Shifting the opening balance shifts every balance equally,
   so one trial run gives the exact answer.

**Determinism:** one `random.Random` seeded from scenario + seed. Fixed English month names (not
locale-dependent `strftime`) and LF line endings make output byte-identical on every machine.
A test fails if `data/synthetic/` is stale.

**Scenarios (seed 42):**

| Scenario | Story | Key facts |
|---|---|---|
| `cash_crunch` | Thin-margin distributor. A S$85,000 stock bill is due 2026-11-05, and two big customers pay 22–25 days late | Opening balance S$171k (calibrated). Lowest balance in the history +S$19.9k. Forward low −S$17.8k on 2026-11-05 (week 6). A second dip to −S$8.9k in week 10. Accrual net loss −S$22.5k for the year |
| `concentrated_b2b` | IT services firm, one client ≈ 61% of invoiced revenue, one slow payer (~40 days late) | Healthy cash throughout. One overdue invoice as of 2026-09-30. Accrual net profit S$73.3k |

### Accrual inputs and answer key (chunk 11)

Chunk 12 builds an accrual P&L, an indirect cash flow and a balance sheet. Chunk 11 added the
source data those need, plus the answer key. It uses a **separate random generator**
(`<scenario>:<seed>:accrual`), so adding it changed no existing row. The one deliberate
exception is GST (below).

| Input (CSV) | How the truth makes it |
|---|---|
| `gst` column on invoices and bills | Amounts are GST-inclusive; gst = amount × 9/109, rounded half up |
| GST payments (29 Jan/Apr/Jul/Oct) | Each is the previous quarter's return: output tax − input tax, exact. Input tax is claimed **on supplier bills only** (rent, utilities and software have no tax invoice in our data, a stated simplification). Warm-up documents (Jul–Sep 2025) supply Q3 2025, paid 29 Oct 2025. The old noisy draw is still made and then discarded, so every other row is unchanged |
| `opening_balances.csv` (30 Sep 2025) | Cash = account openings; receivables/payables = documents open that day; stock, fixed assets, loan, GST (Q3 2025 return) and CPF (Sep 2025 run) from the inputs below; share capital set; **retained earnings is the balancing figure** |
| `inventory_snapshots.csv` (cash_crunch) | Month-end stocktake ≈ S$45k × noise (6%), plus the unsold S$85k bulk-stock bill net of GST from 21 Sep 2026. Periodic method: cost of sales = opening stock + bills issued (net) − closing stock; asserted positive |
| `fixed_assets.csv` | Bought before the window (no bank transaction). Straight line from the month after purchase down to the residual value. Accumulated depreciation is rounded cumulatively, so the months never drift |
| `loans.csv` + `loan_schedule.csv` (cash_crunch) | TL-20817 at 6.5% over 60 months. Principal S$214,656.45 is solved so that the instalment is exactly the S$4,200 in the bank. Reducing balance: interest = round(balance × rate/12), principal = 4,200 − interest; only the last instalment (2028) absorbs rounding. Checked against all 12 bank repayments |
| `payroll_runs.csv` | Net pay = the salary transaction. Total CPF = the fixed CPF payment of the *next* month (14th), split 20:17 between employee and employer. Gross = net + employee CPF. Payroll cost = gross + employer CPF (equal to cash, since CPF is constant) |

**Answer key** (`ground_truth.json["accrual"]`): opening balance sheet; for each month Oct 2025 →
Sep 2026 the P&L lines (GST-exclusive revenue, purchases, cost of sales, operating expenses by line
incl. depreciation, interest, net profit), the balance sheet (cash, receivables, stock, fixed
assets cost / accumulated depreciation / net, payables, GST payable, CPF payable, loan, share
capital, retained earnings, totals), the indirect cash flow (net profit + depreciation +
working-capital changes = operating; loan principal = financing; interest stays in operating),
and `checks`; GST returns per quarter; the loan's principal, balance and interest in the window.
**The generator refuses to write data unless, every month, assets − liabilities − equity = 0.00 and
closing cash from the cash flow = the bank balance.** That makes the key self-consistent by
construction, and it doesn't depend on any code chunk 12 will write.

**prompt_injection** copies cash_crunch's inputs and key. Because INV-1064 is shown open while its
receipt is in the bank, receivables computed from its documents will differ from the key until the
invoice is linked. That is the same deliberate difference as before.

**Effect on the forecast.** With GST on documents, the forecast puts a quarterly GST payment whose
quarter has already ended at output − input tax for that quarter
(`cashflow.forecast.gst_return`), and stops repeating last quarter's amount. cash_crunch's 29 Oct
payment is S$9,867.75, not S$16,055.60: the S$85k stock bill brings S$7,018 of input tax. This
keeps the December funding need at S$13,025.81 (it was S$13,260.76). Repeating history would have
inflated it to S$19,213.66.

## Accrual statements (`src/copilot/analysis/statements.py`, chunk 12)

**Goal:** a monthly profit and loss, balance sheet and indirect cash flow, built from the books
the app holds (never from `ground_truth.json`), that balance from real lines, with no balancing
figure.

**Method: double entry, rolled forward.** Start from the opening balance sheet. Each month,
every document and every bank transaction moves exactly one pair of lines:

| Event | Lines moved |
|---|---|
| Invoice issued | receivables + amount; revenue + (amount − GST); GST owed + GST |
| Bill issued | payables + amount; purchases + (amount − GST); GST owed − GST |
| Receipt that settles an invoice | cash +; receivables − |
| Payment that settles a bill | cash −; payables − |
| Customer money in that no invoice claims | cash +; "customer payments not yet matched" + (liability) |
| Supplier money out that no bill claims | cash −; "supplier payments not yet matched" + (asset) |
| GST payment (category tax) | cash −; GST owed − |
| Salary or CPF payment (category payroll) | cash −; CPF and wages owed − |
| Payroll run for the month | payroll cost + (gross + employer CPF); CPF and wages owed + |
| Loan repayment | cash −; interest (P&L) + the schedule row's interest; loan − the rest |
| Rent, utilities, software, marketing, professional fees, other, **uncategorised** money out | cash −; that operating expense + |
| Month-end | cost of sales = opening stock + purchases − closing stock (stocktake); depreciation + (accumulated depreciation +) |

Because every pair is equal and opposite, assets − liabilities − equity stays at the opening
difference, which is refused unless it is 0.00. Cash on the balance sheet is the bank (account
openings + transactions), not a derived figure, so the two monthly checks are real:
`balance_sheet_difference` and `closing_cash_minus_bank` (cash-flow closing cash − bank). Both
are 0.00 every month in all three scenarios.

**Which transaction settles which document:** receipt links first (the sandbox or
`mark_invoice_paid`), then `reconcile.match_settlements` (same counterparty, exact amount, on or
after issue), each transaction used once. A paid document with no matching payment stays in
receivables/payables with a warning, rather than being assumed paid on its due date as DSO does:
the statements must never disagree with the bank.

**Unmatched money gets its own line (Daniel, 2026-10-11).** prompt_injection's INV-1064 is still
marked unpaid while its S$8,005.63 receipt (t00201, 20 Sep) is in the bank. Its September
balance sheet shows receivables S$8,005.63 above the answer key and an equal "customer payments
not yet matched to an invoice" liability; equity, profit and every other line match the key, and
it balances. Once the owner links the receipt, every line matches the key exactly. Guessing the
match would be the app deciding what `mark_invoice_paid` exists for the owner to confirm.

**Other rules:**
- Depreciation: straight line from the month after purchase, down to the residual value; the
  accumulated amount is rounded half up cumulatively, so months never drift.
- Uncategorised money out counts as "other" operating costs. The categoriser leaves 10
  (cash_crunch) / 9 (b2b) vague "other" payments uncategorised; with this rule every line
  matches the key, and a warning gives the count.
- Loan repayments are matched to the schedule row due in the same month with the same instalment;
  the balance-sheet loan is split into principal due within 12 months (schedule) and after.
- Other income, owner drawings and new borrowing have their own lines (zero in our data).
- Interest is in operating cash flow; loan principal in financing; investing is 0 (asset purchases
  inside the period are not supported yet and are left out with a warning).

**Fallbacks (rule 7):** no opening balance sheet → no statements, and the reason names the
missing file and points to cash-basis tools; opening sheet that doesn't balance, has two dates,
or isn't at a month-end → refused with the reason; a month without a stocktake → stock carried,
cost of sales = purchases, warning; a month without a payroll run (e.g. Oct 2026 after the clock
is moved on) → payroll cost = what was paid, warning; opening receivables/payables that differ
from the documents open that day, or a loan balance that differs from the lender's schedule →
warning.

**Periods (Daniel, 2026-10-11):** month, calendar quarter (to date), calendar year to date, last
12 months, ending in any complete month after the opening date up to the sandbox's today. P&L
and cash flow add up the months; the balance sheet is the last month-end. A period that starts
before the books says how many of its months it covers. Ratios: gross, operating and net margin,
EBITDA (operating profit + depreciation), current ratio, debt ratio.

**Results (all match the answer key to the cent):**

| | cash_crunch | concentrated_b2b |
|---|---|---|
| Net profit, Sep 2026 | −S$4,105.30 (operating margin −2.68%) | +S$770.16 |
| Net profit, 12 months to Sep 2026 | −S$22,467.49 (operating margin −1.03%) | +S$73,321.67 (6.18%) |
| Operating cash flow, 12 months | S$24,212.10 | S$104,994.50 |
| Current ratio / debt ratio, 30 Sep 2026 | 2.06x / 48.19% | 6.40x / 14.80% |
| Loan due within 12 months | S$46,610.93 of S$79,406.52 | none |

**Cash versus accrual (the deck point).** `get_metrics` keeps cash margins and adds accrual ones.
cash_crunch, September 2026: operating margin +34.7% on cash basis, −2.7% on accrual. Cash came
in from older invoices while the month's own sales didn't cover its costs.

## Grading task answers (`src/copilot/evals/tasks.py`, chunk 6)

**Value matching.** Every number in the reply is read with its currency sign, thousands commas,
decimals and suffix (k, m, million, %). A written number claims a precision: half a unit of its
last digit, times the suffix. "S$153,161.41" claims ±0.005, "S$153,161" ±0.5, "S$153.2k" ±50,
"16.4%" ±0.05 points. An expected value matches if some number in the reply is within that
precision of it, ignoring sign ("-S$13,260.76" and "S$13,260.76 short" both match). Percent
values must be written with %; a ratio (0.1644) is compared as 16.44. Dates match ISO,
"5 Nov", "November 5th", "5 November 2026" or "5/11/2026".

**Grounding (every turn of every case).** Each S$ amount and percentage in the model's own words
must match, at the precision written, some number in this session's tool results (ratios also
×100) or in the user's messages. Counts, days and ids are not checked. This is the test form of
"the LLM never does arithmetic" and "never invent data": rounding a tool value passes, adding
two tool values fails. It caught a real case on the first Claude run: "COGS and payroll make up
about 85% of spending" (49.8% + 35.3% added by the model). The system prompt now names
percentages and shares explicitly, and the case passes.

**Limits.** A model can still pass by quoting a tool number in the wrong context (right number,
wrong claim), and phrase checks (`any_of`) accept any wording that contains a listed phrase.
Cases are therefore written so the key number or phrase only appears when the answer is right.

## Recorded adjustments and saved assumptions (chunk 13)

**Goal:** let the owner correct what the imported books miss, and tell the forecast what they
know, without overwriting any imported figure (rule 7) and with every change visible and
undoable. Decisions (Daniel, 2026-10-11): three adjustment kinds; staff draft, owner applies;
last 3 complete months only; two assumption kinds; assumptions owner-only.

**Adjustments are non-cash, one pair of lines each** (`statements.py` reads the applied ones):

| Kind | Month M | Month M+1 |
|---|---|---|
| `accrued_cost {month, amount > 0, line}` (rent, utilities, software, marketing, professional fees, other) | that cost line + A; "Accrued costs (recorded adjustments)" liability + A | reversed: cost line − A; liability − A (the real bill or payment lands then) |
| `relabel {transaction_id, to}` (a payment now uncategorised or in a cost line; to a cost line or owner drawings) | the payment is read as the new category: moves between cost lines, or out of profit into owner drawings (equity) | none |
| `stock_count {month, amount ≥ 0}` | month-end stock = the count instead of the stocktake; cost of sales moves the opposite way | opens from the counted stock (automatic) |

No adjustment touches the bank, so closing cash still equals the bank and the balance sheet
still balances with no plug. The accrual auto-reverses because the real bill or payment will be
counted when it arrives; without the reversal the cost would count twice.

**Views:** `financial_statements(view=...)`: `with_adjustments` (default) or `as_imported`. When
an applied adjustment touches the period (an accrual also touches M+1, a stock count also
M+1's opening), `adjustments` lists them with net profit as imported, with adjustments and the
difference. `get_metrics`' accrual block uses the adjusted books and counts the adjustments.
Cash-basis figures stay as imported (risk R44). **Open months:** the last 3 complete months in
the books (`analysis/adjustments.py`); with today 30 Sep 2026: Jul, Aug, Sep.

**Effect preview:** the confirmation restates the exact change in that month's net profit,
computed by building the statements with the adjustment added (or, for undo, left out) without
saving anything (`preview` argument).

**Saved assumptions** (`forecast_13_weeks(use_saved=True)`):
- `payment_delay {customer, days 0–180}` replaces that customer's measured average delay for
  open and expected invoices.
- `recurring_change {category, monthly amount, start}`: that monthly recurring cost uses the new
  amount from `start` (GST can't be changed this way).
They are listed in `saved_assumptions`; `forecast_balance` also returns
`low_point_without_saved`. Alerts, recommendations, financing need and what-if all start from
the forecast with saved assumptions. What-if stays temporary.

**Results (cash_crunch, all from the answer key ± the known amount):**

| Adjustment | Effect |
|---|---|
| S$2,000 professional fees accrued for Sep 2026 | Sep net profit −S$4,105.30 → −S$6,105.30 (reverses in Oct, once Oct is in the books) |
| The same accrual for Aug 2026 | Aug −S$2,000, Sep +S$2,000 (reversal); 12-month total unchanged (−S$22,467.49) |
| t00158 (S$307.50 "MISC DEBIT", 2 Jul) → owner drawings | Jul net profit −S$7,282.39 → −S$6,974.89; total equity unchanged |
| Sep stock counted at S$116,343.55 (books S$117,843.55) | Sep cost of sales S$76,475.34 → S$77,975.34; net profit − S$1,500 |
| Undo | back to the answer key exactly |

Both checks are 0.00 in every month, both scenarios, with each kind applied. Saved assumption
"Bayfront pays 43 days after the due date" (measured 22) gives the same low point as the what-if
"Bayfront pays 3 weeks late": −S$70,660.41 on 14 Nov (−S$13,025.81 on 27 Dec without it).
