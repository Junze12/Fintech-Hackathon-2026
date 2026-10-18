# Core algorithms

How Fintellect calculates every number it shows. All of it is plain Python with exact
decimals; the AI never calculates. Examples use the main sample business, **Straits Harbour
Distribution** (`cash_crunch`), as of 30 Sep 2026, unless stated otherwise.

**How results are checked.** The sample businesses are generated from a known "true" model
(customers, suppliers, costs, payment habits), and the generator records the correct answers
separately (`ground_truth.json`). Tests compare our results with those answers, so they are
not checking the code against itself.

## 1. Categorising transactions

Every bank transaction gets a category (sales, cost of goods, payroll, rent, …) by fixed rules,
first match wins:

1. a category already in the data;
2. the customer's or supplier's default category;
3. a keyword in the description plus the direction of money (so "RENT REFUND" coming in isn't
   counted as rent paid);
4. customer money in = sales, supplier money out = cost of goods;
5. otherwise **uncategorised** (never guessed; reported with a warning).

Rules, not AI: categories decide what counts as revenue or cost, so they must be repeatable,
and a description can't talk its way into a category. Coverage on the samples is 95%, with
100% accuracy on what is categorised; the rest are deliberately vague descriptions.

## 2. Customer payment habits

Each paid invoice is matched to the earliest unused receipt from the same customer for exactly
the same amount, on or after the issue date. Delay = receipt date − due date. Each customer's
average delay times their future receipts (e.g. Bayfront pays 22.5 days late on average).
Unmatched invoices are reported, not guessed.

## 3. Business analysis

**Cash basis** (what actually moved through the bank): revenue, cost of goods, operating costs,
gross and operating margin, net cash flow, and runway (cash ÷ average monthly net outflow over
3 months).

**Invoice basis** (needs invoices and bills): days to get paid (DSO), days to pay suppliers
(DPO), cash conversion cycle (DSO − DPO; stock days left out, with a warning), and the largest
customer's and supplier's share.

**Health measures:** receivables and payables by age (not due, 1–30, 31–60, 61–90, 90+ days),
cash trend over 12 months, debt service cover (cash available ÷ loan repayments), break-even
sales (operating costs ÷ gross margin) and net working capital.

**Comparisons:** any two periods side by side, with the categories that moved most and the
customers or suppliers behind each move ("sales fell S$85,702.43: Bayfront paid 1 invoice
instead of 2").

Every result states its basis. Why both: cash margins swing with payment timing. In August,
Straits Harbour's cash gross margin was −13.9% only because customers paid late; DSO rose from
37.2 to 51.5 days in the same month, which shows the real problem is collections.

## 4. Accrual statements (profit and loss, balance sheet, cash flow)

Built by double entry from the opening balance sheet, month by month. Each event moves one
pair of lines: an invoice raises receivables and revenue (excluding 9% GST); a receipt moves
receivables to cash; a payroll run adds payroll cost and wages owed; a loan repayment splits
into interest and principal using the lender's schedule; month-end stock counts give cost of
sales; assets are depreciated straight-line.

Two checks run every month and must be exactly zero: assets − liabilities − equity, and the
cash-flow statement's closing cash − the bank balance. Cash is never a balancing figure. Money
that no document explains gets its own visible line instead of a guess.

Result: every line matches the generator's answers to the cent, for all 12 months, in both
sample businesses. Straits Harbour, 12 months to Sep 2026: net loss −S$22,467.49, while cash
looked fine.

## 5. 13-week cash forecast

Week by week (Monday to Sunday), starting from today's total cash, adding items from most to
least certain:

1. payments the owner has already confirmed;
2. open bills, on their due date;
3. open invoices, on their due date **plus that customer's usual delay**;
4. expected future invoices and bills, from each customer's and supplier's last 6 months
   (how often, which day, typical amount);
5. recurring costs (rent, payroll, CPF, utilities, loan, quarterly GST), found by grouping past
   payments by day of month: monthly if seen in 5 of the last 6 months, quarterly if seen in 3
   of the last 12 in the same month of the quarter.

With under 8 weeks of history, only known items are used, with a warning. Result: the first
day below zero is **5 Nov 2026**, exactly matching the true answer; lowest point −S$13,025.81
on 27 Dec.

## 6. Alerts

| Alert | Fires when | Severity |
|---|---|---|
| Below your floor | a forecast day is below the owner's floor (default: one month of fixed costs) | critical if it goes below zero, else warning |
| Can't cover a payment | a stretch below zero; names the biggest payment due in it | critical |
| Overdue invoice | an invoice is past due | info if within that customer's usual delay, else warning |
| Books check | a high-severity bookkeeping error exists (section 12) | warning |

Ranked by severity, then S$ at stake × urgency (urgency halves every two weeks). Moving the
simulated clock forward re-runs the alerts and reports new ones.

## 7. What-if and recommendations

**What-if:** up to 5 changes applied to a copy of the forecast: an invoice paid on time, a
customer or bill delayed, a one-off or monthly cost (e.g. a new hire), a cost paused. The
answer gives the new low point, which gaps close or open, and the change week by week.
Nothing is saved.

**Recommendations**, in this order of preference, each tested on the forecast:

1. **collect:** chase an invoice that would arrive before a gap ends if paid on time;
2. **reschedule:** ask a supplier to accept a bill 14 days later;
3. **cut:** pause discretionary costs (marketing, professional fees, owner drawings);
4. **borrow:** only the amount still missing after steps 1–3.

Steps are kept only if they reduce the shortfall (S$ × days below zero). Straits Harbour:
chasing INV-1062 closes November; December is structural (payroll outruns receipts), leaving a
need of **S$13,025.81 from 6 Dec**.

## 8. Cash stress test (2,000 simulated runs)

The forecast is one path; real customers don't pay on their average day. The stress test
re-runs the 13 weeks 2,000 times. In each run, every customer receipt is delayed by a delay
drawn from **that customer's own past delays**; bills and costs stay fixed. A run fails if cash
goes below zero on any day.

From the same runs: the share of runs that survive, the most likely failure day, the largest
one-off shock the business can absorb at a 95% target, the extra cash needed to reach 95%, and
a likely range (10th to 90th percentile) for every day. All amounts are exact to the cent; the
seed is fixed, so results repeat.

Straits Harbour: **0% of runs survive**; 83.7% first fail on 5 Nov; S$48,533.79 more cash would
be needed. Clearpath Systems (`concentrated_b2b`): 100% survive.

## 9. Comparing plans under uncertainty

Every combination of non-borrowing steps (chase, reschedule, cut, an early-payment discount),
each with at most one financing choice (none, a credit line, or one of the eligible loans), is
scored on the **same 2,000 runs**: 56 plans for Straits Harbour.

- Assumptions we have no data for are labelled and can be changed: a chased invoice is paid on
  time with 50% chance; 50% of customers take a 2% discount for paying within 10 days.
- A credit line is drawn only on days cash is short. Its limit is the smallest (rounded up to
  S$1,000) that reaches the target.
- Cost = average over runs of fees, interest and discounts given.
- Ranking: reaches the target first, then lowest cost, then fewer steps.

Result: **chase INV-1062 + ask Meridian to wait + a S$29,000 credit line: 96.10% of runs
survive, cost S$521.98.** A term loan sized to the single-forecast gap survives only 48% of
runs, because receipts can come later than average.

## 10. Financing matching

- **Catalogue:** seven illustrative products from fictional lenders, modelled on common
  Singapore SME financing (working-capital loan, micro loan, term loan, invoice financing,
  revolving credit, trade financing, short-term loan).
- **Need:** from the forecast (after non-borrowing steps) or as stated by the owner.
- **Eligibility:** company facts only (years operating, revenue, margin, staff, local
  shareholding, balances), each with its source. Every rule passes, fails or is unknown, with
  a reason ("14 staff; needs at most 10"). Unknown = not eligible.
- **Cost:** the loan is sized so the cash left after fees equals the need, then its dated
  repayments are built (amortising, flat rate, interest-only or drawn per day). Total cost =
  interest + fees; **effective annual rate (EIR)** = the rate at which those dated flows net to
  zero (XIRR, by bisection with exact decimals).
- **Ranking:** keeps cash above zero over 13 weeks, then lowest total S$ cost, then more
  flexible repayment if cash flow is volatile.

Straits Harbour (S$13,025.81 need): trade financing costs **S$169.52 (EIR 16.44%)**. The lowest
rate isn't the lowest cost: a cheaper-rate loan with a S$20,000 minimum costs S$1,021.79.

## 11. Three-year model (Worst / Expected / Best)

A 36-month profit and loss, balance sheet and cash flow, starting from the latest month-end
balance sheet. Expected drivers come from the books, each labelled with its source; Worst and
Best are fixed steps away:

| Driver | Expected | Worst / Best |
|---|---|---|
| Sales growth per year | last 6 vs previous 6 months | −10 / +10 points |
| Cost of sales % | last 12 months | +3 / −3 points |
| Cost increase per year | 3% (our assumption) | 5% / 2% |
| Customer delay | measured | +15 days / on time |

Payroll, loan schedule, GST, depreciation and stock follow the same rules as the statements;
open invoices and bills are timed exactly as in the 13-week forecast. Both statement checks
are zero every month in every case. Straits Harbour, Expected: cash runs out in Jul 2029
(Worst: Apr 2027).

## 12. Break-even and estimated value

- **Break-even sales** per month = operating costs ÷ (1 − cost of sales %), shown for each case
  and today on both cash and accrual basis. Straits Harbour looks covered on cash (S$124,480.60)
  but not on accrual (S$129,629.01).
- **Estimated value:** discounted free cash flow over 3 years plus a terminal value (20%
  discount rate, 2% growth after year 3, 17% tax), and a 4× EBITDA multiple as a cross-check;
  equity = enterprise value − loans + cash. Every input is labelled and can be changed, with
  sensitivity rows beside the result. When the business burns cash, the answer is "not
  meaningful" with the reason, never a made-up number. Always presented as an estimate, not a
  price or advice. Clearpath Systems, Expected: S$576,789.10.

## 13. Books check (reconciliation)

Five passes over the bank and the documents, each record used at most once:

| Check | Severity |
|---|---|
| Same payment twice within 7 days | high |
| Bill overpaid / invoice short-paid or overpaid (within 5%) | high / medium |
| Invoice or bill marked paid with no payment in the bank | high / medium |
| Money in or out that no document explains | medium from S$1,000, else low |
| Supplier statement lists a bill we don't have, or a different amount | high (amount: from S$100 or 1%) |

Result: on the `messy_books` sample (10 planted errors) every error is found with nothing
extra; the clean samples show no high or medium items.

## 14. Corrections by the owner

- **Adjustments** (accrued cost, relabelled payment, stock count) sit beside the imported books,
  never overwrite them, and move one pair of lines, so both statement checks still hold. Staff
  draft, the owner applies with the confirmation code, and the statements can always be shown
  "as imported". Only the last 3 complete months can be adjusted.
- **Saved assumptions** (a customer's payment delay, a changed recurring cost) feed the
  forecast until removed. Owner-only, confirmed, and the forecast also shows the result
  without them.

## 15. Checking the assistant's answers (task suite)

Each case is a scripted conversation with the expected tools and values (from the answer
key). Every S$ amount and percentage in the assistant's reply must match a number in that
session's tool results at the precision written, so a rounded tool figure passes but a sum or
estimate the AI made itself fails. No AI is used to grade.
