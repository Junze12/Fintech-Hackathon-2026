# T-VL-01: When will we break even?

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Straits Harbour covers its costs today on cash basis (break-even S$124,480.60 a month vs S$132,684.45 of sales received, last 3 months), but not on accrual basis, and in the expected case sales stay below break-even for all 3 years (year 1 needs S$129,721.65 a month against about S$126,678 of sales). The answer must give the projected figure, say break-even is not reached within 3 years, and not mix the two bases silently.

## Conversation

### Turn 1

**User:**

> When will we break even, and how far are we from it?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_break_even_and_value` | {"part": "break_even"} | **ok** | ok |
| `get_health_ratios` |  | **ok** | ok |

<details><summary>Tool result data</summary>

`get_break_even_and_value`

```json
{
  "value": {
    "starts_from": "2026-09-30",
    "first_month": "2026-10",
    "last_month": "2029-09",
    "break_even": {
      "today_cash": {
        "basis": "cash",
        "period_start": "2026-07-01",
        "period_end": "2026-09-30",
        "avg_monthly_sales": "132684.45",
        "avg_monthly_fixed_costs": "62451.92",
        "gross_margin": "0.5017",
        "break_even_monthly_sales": "124480.60",
        "headroom": "8203.85"
      },
      "today_accrual": {
        "basis": "accrual",
        "period_start": "2025-10-01",
        "period_end": "2026-09-30",
        "avg_monthly_sales": "126970.37",
        "avg_monthly_fixed_costs": "63997.84",
        "gross_margin": "0.4937",
        "break_even_monthly_sales": "129629.01",
        "headroom": "-2658.64"
      },
      "cases": {
        "worst": {
          "case": "worst",
          "name": "Worst",
          "basis": "accrual",
          "gross_margin": "0.4637",
          "years": [
            {
              "year": 1,
              "months": "Oct 2026 - Sep 2027",
              "avg_monthly_sales": "113981.30",
              "avg_monthly_fixed_costs": "64043.58",
              "break_even_monthly_sales": "138114.25",
              "headroom": "-24132.95"
            },
            {
              "year": 2,
              "months": "Oct 2027 - Sep 2028",
              "avg_monthly_sales": "102321.01",
              "avg_monthly_fixed_costs": "66918.68",
              "break_even_monthly_sales": "144314.59",
              "headroom": "-41993.58"
            },
            {
              "year": 3,
              "months": "Oct 2028 - Sep 2029",
              "avg_monthly_sales": "91853.57",
              "avg_monthly_fixed_costs": "70200.03",
              "break_even_monthly_sales": "151391.04",
              "headroom": "-59537.47"
            }
          ],
          "first_month_reached": null,
          "months_below": 36,
          "status": "Sales stay below break-even for all 3 years.",
          "monthly": []
        },
        "expected": {
          "case": "expected",
          "name": "Expected",
          "basis": "accrual",
          "gross_margin": "0.4937",
          "years": [
            {
              "year": 1,
              "months": "Oct 2026 - Sep 2027",
              "avg_monthly_sales": "126678.34",
              "avg_monthly_fixed_costs": "64043.58",
              "break_even_monthly_sales": "129721.65",
              "headroom": "-3043.31"
            },
            {
              "year": 2,
              "months": "Oct 2027 - Sep 2028",
              "avg_monthly_sales": "126386.98",
              "avg_monthly_fixed_costs": "65668.64",
              "break_even_monthly_sales": "133013.24",
              "headroom": "-6626.26"
            },
            {
              "year": 3,
              "months": "Oct 2028 - Sep 2029",
              "avg_monthly_sales": "126096.29",
              "avg_monthly_fixed_costs": "67599.94",
              "break_even_monthly_sales": "136925.13",
              "headroom": "-10828.84"
            }
          ],
          "first_month_reached": null,
          "months_below": 36,
          "status": "Sales stay below break-even for all 3 years.",
          "monthly": []
        },
        "best": {
          "case": "best",
          "name": "Best",
          "basis": "accrual",
          "gross_margin": "0.5237",
          "years": [
            {
              "year": 1,
              "months": "Oct 2026 - Sep 2027",
              "avg_monthly_sales": "139375.37",
              "avg_monthly_fixed_costs": "64043.58",
              "break_even_monthly_sales": "122290.58",
              "headroom": "17084.79"
            },
            {
              "year": 2,
              "months": "Oct 2027 - Sep 2028",
              "avg_monthly_sales": "152992.35",
              "avg_monthly_fixed_costs": "65043.62",
              "break_even_monthly_sales": "124200.15",
              "headroom": "28792.20"
            },
            {
              "year": 3,
              "months": "Oct 2028 - Sep 2029",
              "avg_monthly_sales": "167939.70",
              "avg_monthly_fixed_costs": "66318.66",
              "break_even_monthly_sales": "126634.82",
              "headroom": "41304.88"
            }
          ],
          "first_month_reached": "2026-10",
          "months_below": 0,
          "status": "Sales are at or above break-even every month.",
          "monthly": []
        }
      }
    },
    "valuation": null
  },
  "drivers": [
    {
      "label": "<untrusted>Expected case: break-even</untrusted>",
      "amount": null,
      "detail": "<untrusted>Sales stay below break-even for all 3 years.</untrusted>"
    },
    {
      "label": "<untrusted>Expected case: DCF equity value</untrusted>",
      "amount": null,
      "detail": "<untrusted>not meaningful</untrusted>"
    },
    {
      "label": "<untrusted>Expected case: EBITDA multiple equity value</untrusted>",
      "amount": null,
      "detail": "<untrusted>not meaningful</untrusted>"
    },
    {
      "label": "<untrusted>Book value of equity (accounting, not a price)</untrusted>",
      "amount": "275619.06",
      "detail": "<untrusted></untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2025-10-01",
    "period_end": "2026-09-30",
    "record_count": 12
  },
  "warnings": [
    "An estimate from your books and the stated assumptions, not advice and not a price. A buyer or lender would do their own valuation.",
    "Best case: 67% of the DCF value comes after year 3, so it rests mostly on the business carrying on as projected.",
    "No owner salary deducted: we can't tell whether payroll includes the owner. If the owner works unpaid, a buyer would deduct a market salary (give one to see the effect).",
    "Tax is a flat 17% of positive operating profit (partial exemption and past losses not applied). Break-even and EBITDA are before tax."
  ]
}
```

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

> **Short answer:** On the expected case, you don't break even in the next 3 years. You're close, though.
>
> **Where you are now**
> - **Cash basis, last 3 months:** Average monthly sales are S$132,684.45. Break-even is S$124,480.60. You're S$8,203.85 above it.
> - **Accrual basis, last 12 months:** Average monthly sales are S$126,970.37. Break-even is S$129,629.01. You're S$2,658.64 below it.
> - The two bases disagree because the recent 3 months were stronger than the 12-month average. Accrual is the better guide to profitability.
>
> **Break-even sales per month (accrual, 3-year model)**
>
> | Case | Year 1 | Year 3 | Reached? |
> |---|---|---|---|
> | Expected | S$129,721.65 needed vs S$126,678.34 sales (S$3,043.31 short) | S$136,925.13 needed vs S$126,096.29 sales (S$10,828.84 short) | Not within 3 years |
> | Worst | S$24,132.95 short | S$59,537.47 short | Not within 3 years |
> | Best | S$17,084.79 above | S$41,304.88 above | From Oct 2026 |
>
> **Why the gap widens in the expected case:** Sales stay flat to slightly down, and fixed costs rise from S$64,043.58 to S$67,599.94 a month. The gross margin is 49.37%.
>
> **What would close the gap:** You need about S$3k more in monthly sales, or lower costs or a better margin. Tell me a sales growth rate, a cost cut or a margin figure, and I'll re-run it.
>
> **Also relevant:** Loan repayments of S$50,400.00 over the last 12 months were not covered by operating cash. Debt service cover is 0.61.

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 2.

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
| biz-straits | yes | 2 | `4a49385f1f0002c44d9078c19ffd62cb834abeec7253c15e326f148c65238424` |

Claude usage for this case: 2 calls, about US$0.027.
