# T-AN-08: Debt service cover and break-even sales

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Lender-style checks. Over the last 12 months Straits Harbour's cash after running the business covers its loan repayments 1.46 times; it needs about S$124.5k of sales a month to break even and recently averaged S$132.7k.

## Conversation

### Turn 1

**User:**

> Can we afford our loan repayments, and how much do we need to sell each month to break even?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_health_ratios` |  | **ok** | ok |

<details><summary>Tool result data</summary>

`get_health_ratios`

```json
{
  "debt_service_cover": {
    "value": {
      "start": "2025-10-01",
      "end": "2026-09-30",
      "basis": "cash",
      "cash_available": "30926.85",
      "debt_service": "50400.00",
      "dscr": "0.61"
    },
    "drivers": [
      {
        "label": "<untrusted>Cash from operations after tax and drawings</untrusted>",
        "amount": "30926.85",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Loan repayments</untrusted>",
        "amount": "-50400.00",
        "detail": "<untrusted></untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2025-10-01",
      "period_end": "2026-09-30",
      "record_count": 206
    },
    "warnings": [
      "Cash basis: uses bank transactions, not audited accounts",
      "The data has loan repayments but no loan balance or interest/principal split, so leverage and interest cover can't be measured",
      "Below 1.0: the business's own cash did not cover its loan repayments",
      "10 uncategorised payments (-S$2,447.75) are counted as operating costs, to be safe; uncategorised receipts are left out"
    ]
  },
  "break_even": {
    "value": {
      "start": "2026-07-01",
      "end": "2026-09-30",
      "basis": "cash",
      "avg_monthly_revenue": "132684.45",
      "avg_monthly_fixed_costs": "62451.92",
      "gross_margin": "0.5017",
      "break_even_monthly_sales": "124480.60",
      "headroom": "8203.85"
    },
    "drivers": [
      {
        "label": "<untrusted>Average monthly sales received</untrusted>",
        "amount": "132684.45",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Average monthly fixed costs</untrusted>",
        "amount": "-62451.92",
        "detail": "<untrusted></untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2026-07-01",
      "period_end": "2026-09-30",
      "record_count": 50
    },
    "warnings": [
      "Cash basis: stock bought in one month and sold in another makes the margin swing; averaging 3 months smooths some of that",
      "Fixed costs are operating expenses (payroll, rent, utilities, ...); tax and loan repayments are not included",
      "1 uncategorised payments (-S$307.50) are counted as operating costs, to be safe; uncategorised receipts are left out"
    ]
  }
}
```

</details>

**Assistant:**

> **Loan repayments: not comfortably.** On a cash basis over the last 12 months (Oct 2025 to Sep 2026), the business had S$30,926.85 left after running costs, tax and owner drawings. Loan repayments were S$50,400.00. That gives a debt service cover of 0.61, and anything below 1.0 means the business's own cash didn't cover the repayments. The shortfall had to come from other sources, such as existing cash.
>
> **Break-even:** based on the last 3 months (Jul to Sep 2026, cash basis), you need about S$124,480.60 a month in sales to cover operating costs.
> - Average monthly sales received: S$132,684.45
> - Headroom: S$8,203.85 a month
> - Average monthly fixed costs: S$62,451.92
> - Gross margin: 50.17%
>
> **Caveats**
> - Break-even leaves out tax and loan repayments. Once repayments are included, the headroom looks thin.
> - The data has no loan balance or interest/principal split, so I can't assess leverage or interest cover.
> - 10 uncategorised payments (S$2,447.75) are counted as operating costs to be safe.
>
> I can run the 13-week cash forecast or compare financing options if you'd like.

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 1.

None: no write was attempted.

## Sandbox bank operations

None: the sandbox bank was not asked to move or record any money.

**Balances:**

| Account | Before | After | Change |
|---|---|---|---|
| Operating account ••••8886 | S$151,526.85 | S$151,526.85 | S$0.00 |
| Reserve account ••••1570 | S$5,000.00 | S$5,000.00 | S$0.00 |

## Audit hash chain

| Business | Verified | Entries | Head hash |
|---|---|---|---|
| biz-straits | yes | 1 | `6b626c27a608757c3aa98955582b8bd5af594b9d8e5c09079e2f468b744e6818` |

Claude usage for this case: 2 calls, about US$0.019.
