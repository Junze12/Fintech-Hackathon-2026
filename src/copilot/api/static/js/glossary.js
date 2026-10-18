// Plain-English meanings of the terms on the dashboard. One list feeds both the (i) icons next
// to labels (ui.term / ui.info) and the Glossary page, so the two can't disagree. Text only:
// no figures from the books, just the fixed method settings the code uses.

export const GROUPS = ["Cash", "Cash plan", "Outlook", "Statements", "Books check"];

export const TERMS = {
  // --- Cash ---------------------------------------------------------------------------------
  cash_today: { group: "Cash", term: "Cash today", text: "The balance across all business bank accounts on the simulated date shown in the top bar." },
  lowest_point: { group: "Cash", term: "Lowest point", text: "The lowest end-of-day balance in the 13-week forecast. Customer payments are timed by how late each customer has paid in the past, not by the due date." },
  forecast: { group: "Cash", term: "13-week forecast", text: "A day-by-day projection of the bank balance from scheduled bills, payroll, rent, tax, loan instalments, recurring costs found in your history, and expected customer payments." },
  cash_floor: { group: "Cash", term: "Cash floor", text: "The balance you don't want to go below. An alert fires when the forecast drops under it." },
  band: { group: "Cash", term: "P10–P90 band", text: "Where 80% of the simulated runs land. 1 run in 10 ends below the band (P10) and 1 in 10 above it (P90); the middle line (P50) is the typical run." },
  overdue: { group: "Cash", term: "Overdue invoice", text: "A customer invoice that is past its due date and not yet paid." },
  days_late: { group: "Cash", term: "Average days late", text: "How many days after the due date a customer has paid, on average, across their past invoices." },
  paid_by_due: { group: "Cash", term: "Paid by due date", text: "The share of a customer's past invoices that were paid on or before the due date." },
  gross_margin: { group: "Cash", term: "Gross margin", text: "Sales minus the cost of the goods sold, as a share of sales." },
  operating_margin: { group: "Cash", term: "Operating margin", text: "What is left of sales after cost of sales and running costs (payroll, rent and so on), as a share of sales." },
  runway: { group: "Cash", term: "Runway", text: "Cash divided by the average monthly net outflow over the last 3 months. Only shown when more money goes out than comes in." },
  dso: { group: "Cash", term: "Days to get paid (DSO)", text: "Unpaid customer invoices at period end divided by sales in the period, times the days in the period. Lower is better." },
  dscr: { group: "Cash", term: "Debt service cover", text: "Cash from operations after tax and owner drawings, divided by loan repayments, over the last 12 months. Below 1 means the business doesn't earn enough to cover its loan payments." },
  basis_cash: { group: "Cash", term: "Cash basis", text: "Counts money when it moves through the bank: a sale counts when the customer pays." },

  // --- Cash plan ----------------------------------------------------------------------------
  survival: { group: "Cash plan", term: "Survival", text: "The share of 2,000 simulated runs in which cash never drops below zero (or your floor) over the next 13 weeks. Each run redraws when every customer pays, based on that customer's own past delays." },
  target: { group: "Cash plan", term: "Survival target", text: "The survival share a plan must reach to count as safe. 95% by default, which means at most 1 bad run in 20." },
  gap_bridge: { group: "Cash plan", term: "Gap bridge", text: "How cash today becomes the worst likely balance on the riskiest day: bills paid before that day, customer payments received, then a margin for bad luck in payment timing." },
  bad_luck: { group: "Cash plan", term: "Bad-luck margin", text: "The extra cash lost when customers pay later than usual, in the bad run that matches your survival target." },
  extra_buffer: { group: "Cash plan", term: "Extra cash needed", text: "How much more cash you would need today for the survival target to be met without taking any action." },
  best_plan: { group: "Cash plan", term: "Best plan", text: "The cheapest combination of actions that meets the survival target. Ties go to the plan with fewer actions. Every plan is scored on the same 2,000 runs." },
  plan_cost: { group: "Cash plan", term: "Plan cost", text: "What a plan costs compared with doing nothing: financing fees and interest, discounts given and any gross profit lost." },
  short_on: { group: "Cash plan", term: "Short on the riskiest day", text: "How far below zero the balance would be on the riskiest day in the same bad run, with that plan." },
  credit_line: { group: "Cash plan", term: "Credit line", text: "A borrowing limit you draw on only when cash would fall below the floor and repay when cash recovers. Interest is charged only on what is drawn." },
  eir: { group: "Cash plan", term: "Effective annual rate", text: "The full yearly cost of borrowing, including all fees, so products with different fee structures can be compared fairly." },
  total_cost: { group: "Cash plan", term: "Total cost", text: "All interest and fees in S$ for the amount and period you actually need." },
  funding_need: { group: "Cash plan", term: "Amount to borrow", text: "The gap left after the steps that don't involve borrowing, from the forecast: how much, from when and for how long." },

  // --- Outlook ------------------------------------------------------------------------------
  cases: { group: "Outlook", term: "Worst, Expected and Best case", text: "Expected uses the trends measured in your books. Worst and Best move each driver a fixed step down or up, so you can see a range rather than one guess." },
  driver: { group: "Outlook", term: "Driver", text: "One input that shapes the 3-year model: sales growth, cost of sales %, cost increases, customer delay, owner drawings and one-off events." },
  sales_growth: { group: "Outlook", term: "Sales growth", text: "Yearly change in sales, measured from the last 6 months compared with the 6 before, annualised." },
  cost_of_sales_pct: { group: "Outlook", term: "Cost of sales %", text: "The cost of the goods sold as a share of sales, over the last 12 months." },
  customer_delay: { group: "Outlook", term: "Customer delay", text: "Days after the due date that customers are assumed to pay." },
  break_even: { group: "Outlook", term: "Break-even sales", text: "The monthly sales needed to cover running costs: monthly operating costs divided by the gross margin (1 minus cost of sales %), before interest." },
  dcf: { group: "Outlook", term: "Discounted cash flow (DCF)", text: "A value estimate: the free cash flow of years 1–3 and a value for the years after, each reduced for how far in the future it is. Not meaningful when the business still uses cash in year 3." },
  discount_rate: { group: "Outlook", term: "Discount rate", text: "The yearly return a buyer would want for the risk of a small business. Future cash is reduced at this rate. 20% by default." },
  terminal_growth: { group: "Outlook", term: "Growth after year 3", text: "How fast free cash flow is assumed to grow each year after the 3-year model ends. 2% by default." },
  ebitda: { group: "Outlook", term: "EBITDA", text: "Earnings before interest, tax, depreciation and amortisation: operating profit with depreciation added back." },
  ebitda_multiple: { group: "Outlook", term: "EBITDA multiple", text: "A quick value estimate: year-1 EBITDA times a multiple (4× by default). Not meaningful when EBITDA is zero, negative or tiny." },
  free_cash_flow: { group: "Outlook", term: "Free cash flow", text: "Cash from operations before interest, minus any owner salary and an estimated 17% tax on profit. It is the cash a buyer could take out." },
  enterprise_value: { group: "Outlook", term: "Enterprise value", text: "The value of the business's operations, before counting its cash and loans." },
  equity_value: { group: "Outlook", term: "Equity value", text: "What the owner's share is worth: enterprise value plus cash, minus loans." },

  // --- Statements ---------------------------------------------------------------------------
  basis_accrual: { group: "Statements", term: "Accrual basis", text: "Counts sales and costs when they are earned or incurred (the invoice or bill date), not when the money moves. This is how the statements are built." },
  pnl: { group: "Statements", term: "Profit and loss", text: "Sales minus all costs for the period, ending in net profit." },
  gross_profit: { group: "Statements", term: "Gross profit", text: "Sales minus the cost of the goods sold." },
  operating_profit: { group: "Statements", term: "Operating profit", text: "Gross profit minus running costs such as payroll, rent and depreciation, before interest." },
  net_profit: { group: "Statements", term: "Net profit", text: "Operating profit plus other income, minus interest. Income tax is not included." },
  net_margin: { group: "Statements", term: "Net margin", text: "Net profit as a share of sales." },
  depreciation: { group: "Statements", term: "Depreciation", text: "The part of an equipment or vehicle purchase counted as a cost each month over its useful life. No cash moves." },
  balance_sheet: { group: "Statements", term: "Balance sheet", text: "What the business owns (assets), owes (liabilities) and what belongs to the owner (equity) on one date. Assets always equal liabilities plus equity." },
  receivables: { group: "Statements", term: "Customer invoices unpaid", text: "Money customers owe for invoices already sent (receivables)." },
  payables: { group: "Statements", term: "Supplier bills unpaid", text: "Money owed to suppliers for bills already received (payables)." },
  stock: { group: "Statements", term: "Stock", text: "Goods bought and not yet sold, valued at cost (inventory)." },
  gst: { group: "Statements", term: "GST owed", text: "GST collected on sales minus GST paid on supplier bills, not yet paid to IRAS. It is paid quarterly." },
  cpf: { group: "Statements", term: "CPF owed", text: "Employer and employee CPF contributions from payroll, due the following month." },
  accrued: { group: "Statements", term: "Accrued costs", text: "Costs that belong to this period but haven't been billed yet, recorded as an adjustment." },
  retained: { group: "Statements", term: "Retained earnings", text: "All past profits kept in the business, minus losses." },
  drawings: { group: "Statements", term: "Owner drawings", text: "Money the owner took out of the business for personal use. It is not a cost of the business." },
  unmatched: { group: "Statements", term: "Payments not yet matched", text: "Money received or paid that isn't tied to an invoice or bill yet. Shown on its own line so nothing is lost." },
  cash_flow: { group: "Statements", term: "Cash flow statement", text: "Explains how cash changed in the period: from operations, from investing (equipment) and from financing (loans and owner drawings)." },
  indirect: { group: "Statements", term: "Indirect method", text: "Builds cash from operations by starting with net profit, adding back costs that moved no cash, then adjusting for changes in working capital." },
  working_capital: { group: "Statements", term: "Working capital", text: "Money tied up in day-to-day trading: unpaid invoices and stock minus unpaid bills and taxes. When it grows, cash falls." },
  current_ratio: { group: "Statements", term: "Current ratio", text: "Assets that turn into cash within a year, divided by what must be paid within a year. Above 1 means short-term debts are covered." },
  adjustments: { group: "Statements", term: "Adjustment", text: "A correction you recorded beside the imported books (an accrued cost, a relabelled payment or a stock count). It can be undone; the imported data is never changed." },

  // --- Books check --------------------------------------------------------------------------
  severity: { group: "Books check", term: "Severity", text: "High: likely money lost or a missing bill.\nMedium: amounts that don't match.\nLow: small or unexplained items worth a look." },
  duplicate: { group: "Books check", term: "Possible duplicate payment", text: "Two payments from the same account to the same payee for the same amount within 7 days." },
  unlinked: { group: "Books check", term: "Unlinked payment", text: "A payment that matches an invoice or bill exactly but was never linked to it, so the document still looks unpaid." },
  supplier_statement: { group: "Books check", term: "Supplier statement", text: "The list of bills a supplier says it sent you. Each line is compared with the bills in your books." },
};
