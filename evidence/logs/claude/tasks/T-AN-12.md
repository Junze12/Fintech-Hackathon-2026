# T-AN-12: Cash came in, but was September profitable?

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** The cash-versus-profit trap. September's cash-basis operating margin is +34.7% (old receivables were collected), but on accrual basis Straits Harbour lost money: net profit for September 2026 is negative and the operating margin is about -2.7%.

## Conversation

### Turn 1

**User:**

> Lots of money came in this September. Were we really profitable that month?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_metrics` | {"start": "2026-09-01", "end": "2026-09-30"} | **ok** | ok |
| `get_financial_statements` | {"month": "2026-09", "period": "month", "statement": "pnl"} | **ok** | ok |

<details><summary>Tool result data</summary>

`get_metrics`

```json
{
  "period": {
    "value": {
      "start": "2026-09-01",
      "end": "2026-09-30",
      "basis": "cash",
      "revenue": "196407.51",
      "cogs": "66154.40",
      "opex": "62083.08",
      "gross_margin": "0.6632",
      "operating_margin": "0.3471",
      "net_cash_flow": "63970.03",
      "uncategorised_count": 0,
      "uncategorised_net": "0"
    },
    "drivers": [
      {
        "label": "<untrusted>Revenue (sales received)</untrusted>",
        "amount": "196407.51",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Cost of goods sold</untrusted>",
        "amount": "-66154.40",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Operating expenses</untrusted>",
        "amount": "-62083.08",
        "detail": "<untrusted></untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2026-09-01",
      "period_end": "2026-09-30",
      "record_count": 18
    },
    "warnings": [
      "Cash basis: revenue and costs are counted when money moves, not when invoiced"
    ]
  },
  "accrual": {
    "basis": "accrual",
    "revenue": "136528.55",
    "gross_margin": "0.4399",
    "operating_margin": "-0.0268",
    "net_margin": "-0.0301",
    "net_profit": "-4105.30",
    "adjustments_included": 0
  },
  "working_capital": {
    "value": {
      "start": "2026-09-01",
      "end": "2026-09-30",
      "basis": "invoice",
      "days": 30,
      "invoiced_sales": "148816.13",
      "receivables": "186593.99",
      "dso": "37.6",
      "bills_received": "163982.73",
      "payables": "159271.06",
      "dpo": "29.1",
      "ccc": "8.5",
      "cash": "156526.85",
      "net_working_capital": "183849.78"
    },
    "drivers": [
      {
        "label": "<untrusted>Receivables at period end</untrusted>",
        "amount": "186593.99",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Payables at period end</untrusted>",
        "amount": "-159271.06",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Unpaid invoice INV-1062</untrusted>",
        "amount": "51283.20",
        "detail": "<untrusted>Bayfront Grocers Pte. Ltd., due 2026-10-19</untrusted>"
      },
      {
        "label": "<untrusted>Unpaid invoice INV-1061</untrusted>",
        "amount": "49283.96",
        "detail": "<untrusted>Bayfront Grocers Pte. Ltd., due 2026-10-04</untrusted>"
      },
      {
        "label": "<untrusted>Unpaid invoice INV-1057</untrusted>",
        "amount": "45783.49",
        "detail": "<untrusted>Bayfront Grocers Pte. Ltd., due 2026-09-19</untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2026-09-01",
      "period_end": "2026-09-30",
      "record_count": 117
    },
    "warnings": [
      "Invoice basis: receivables, payables and their days use invoices and bills, not bank receipts",
      "DIO omitted: there is no inventory data, so the cash conversion cycle is DSO - DPO",
      "Net working capital = cash at period end + receivables - payables; no inventory or other short-term debt is in the data"
    ]
  },
  "concentration": {
    "value": {
      "start": "2026-09-01",
      "end": "2026-09-30",
      "basis": "invoice",
      "total_invoiced": "148816.13",
      "largest": {
        "customer_id": "c-bayfront",
        "name": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
        "invoiced": "100567.16",
        "share": "0.6758"
      },
      "customers": [
        {
          "customer_id": "c-bayfront",
          "name": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
          "invoiced": "100567.16",
          "share": "0.6758"
        },
        {
          "customer_id": "c-orchid",
          "name": "<untrusted>Orchid Bay Hospitality</untrusted>",
          "invoiced": "27914.76",
          "share": "0.1876"
        },
        {
          "customer_id": "c-kallang",
          "name": "<untrusted>Kallang Corner Stores</untrusted>",
          "invoiced": "20334.21",
          "share": "0.1366"
        }
      ]
    },
    "drivers": [
      {
        "label": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
        "amount": "100567.16",
        "detail": "<untrusted>67.6% of invoiced sales</untrusted>"
      },
      {
        "label": "<untrusted>Orchid Bay Hospitality</untrusted>",
        "amount": "27914.76",
        "detail": "<untrusted>18.8% of invoiced sales</untrusted>"
      },
      {
        "label": "<untrusted>Kallang Corner Stores</untrusted>",
        "amount": "20334.21",
        "detail": "<untrusted>13.7% of invoiced sales</untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2026-09-01",
      "period_end": "2026-09-30",
      "record_count": 5
    },
    "warnings": [
      "Invoice basis: shares use invoices issued in the period, not bank receipts",
      "One customer accounts for more than 50% of invoiced sales; losing or delaying them would hit cash hard"
    ]
  },
  "supplier_concentration": {
    "value": {
      "start": "2026-09-01",
      "end": "2026-09-30",
      "basis": "invoice",
      "total_billed": "163982.73",
      "largest": {
        "supplier_id": "s-meridian",
        "name": "<untrusted>Meridian Food Imports Pte. Ltd.</untrusted>",
        "billed": "146898.43",
        "share": "0.8958"
      },
      "suppliers": [
        {
          "supplier_id": "s-meridian",
          "name": "<untrusted>Meridian Food Imports Pte. Ltd.</untrusted>",
          "billed": "146898.43",
          "share": "0.8958"
        },
        {
          "supplier_id": "s-harbour",
          "name": "<untrusted>Harbour Freight Lines</untrusted>",
          "billed": "9967.48",
          "share": "0.0608"
        },
        {
          "supplier_id": "s-eastwind",
          "name": "<untrusted>Eastwind Packaging Supplies</untrusted>",
          "billed": "7116.82",
          "share": "0.0434"
        }
      ]
    },
    "drivers": [
      {
        "label": "<untrusted>Meridian Food Imports Pte. Ltd.</untrusted>",
        "amount": "146898.43",
        "detail": "<untrusted>89.6% of supplier bills</untrusted>"
      },
      {
        "label": "<untrusted>Harbour Freight Lines</untrusted>",
        "amount": "9967.48",
        "detail": "<untrusted>6.1% of supplier bills</untrusted>"
      },
      {
        "label": "<untrusted>Eastwind Packaging Supplies</untrusted>",
        "amount": "7116.82",
        "detail": "<untrusted>4.3% of supplier bills</untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2026-09-01",
      "period_end": "2026-09-30",
      "record_count": 5
    },
    "warnings": [
      "Invoice basis: shares use supplier bills issued in the period, not payments",
      "One supplier accounts for more than 50% of purchases; a price rise or delivery problem there would hit the business hard"
    ]
  },
  "runway": {
    "value": {
      "as_of": "2026-09-30",
      "cash": "156526.85",
      "avg_monthly_net_flow": "-5439.99",
      "months": "28.8",
      "status": "burning cash"
    },
    "drivers": [
      {
        "label": "<untrusted>Cash across all accounts</untrusted>",
        "amount": "156526.85",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Average monthly net cash flow, last 3 months</untrusted>",
        "amount": "-5439.99",
        "detail": "<untrusted></untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2026-07-01",
      "period_end": "2026-09-30",
      "record_count": 50
    },
    "warnings": []
  }
}
```

`get_financial_statements`

```json
{
  "value": {
    "basis": "accrual",
    "view": "with_adjustments",
    "period": "Sep 2026",
    "start": "2026-09-01",
    "end": "2026-09-30",
    "months": [
      "2026-09"
    ],
    "pnl": {
      "revenue": "136528.55",
      "purchases": "150442.86",
      "cost_of_sales": "76475.34",
      "gross_profit": "60053.21",
      "operating_expenses": {
        "payroll": "47032.39",
        "rent": "12500.00",
        "utilities": "1875.69",
        "software": "640.00",
        "other": "35.00",
        "depreciation": "1625.00"
      },
      "total_operating_expenses": "63708.08",
      "operating_profit": "-3654.87",
      "other_income": "0.00",
      "interest": "450.43",
      "net_profit": "-4105.30"
    },
    "balance_sheet": null,
    "cash_flow": null,
    "checks": {
      "balance_sheet_difference": "0.00",
      "closing_cash_minus_bank": "0.00",
      "balanced": true,
      "cash_matches_bank": true
    },
    "ratios": {
      "gross_margin": "0.4399",
      "operating_margin": "-0.0268",
      "net_margin": "-0.0301",
      "ebitda": "-2029.87",
      "current_ratio": "2.06",
      "debt_ratio": "0.4819"
    },
    "fixed_assets": [],
    "loans": [],
    "monthly": [],
    "adjustments": null
  },
  "drivers": [
    {
      "label": "<untrusted>Payroll (gross pay + employer CPF)</untrusted>",
      "amount": "47032.39",
      "detail": "<untrusted>operating expense</untrusted>"
    },
    {
      "label": "<untrusted>Rent</untrusted>",
      "amount": "12500.00",
      "detail": "<untrusted>operating expense</untrusted>"
    },
    {
      "label": "<untrusted>Utilities</untrusted>",
      "amount": "1875.69",
      "detail": "<untrusted>operating expense</untrusted>"
    },
    {
      "label": "<untrusted>Unpaid supplier bills</untrusted>",
      "amount": "97828.33",
      "detail": "<untrusted>cash released</untrusted>"
    },
    {
      "label": "<untrusted>Stock</untrusted>",
      "amount": "-73967.52",
      "detail": "<untrusted>cash tied up</untrusted>"
    },
    {
      "label": "<untrusted>Checks</untrusted>",
      "amount": null,
      "detail": "<untrusted>Balance sheet balances; closing cash matches the bank</untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2026-09-01",
    "period_end": "2026-09-30",
    "record_count": 18
  },
  "warnings": [
    "Accrual basis: sales and costs count when invoiced or incurred, not when paid; amounts exclude GST",
    "10 uncategorised payment(s) are counted as other operating costs (real money out that no rule labelled)."
  ]
}
```

</details>

**Assistant:**

> **No. On an accrual basis, September was a small loss.**
>
> - **Accrual net profit: –S$4,105.30.** Revenue was S$136,528.55 and gross profit was S$60,053.21 (44.0% margin). Operating expenses were S$63,708.08, so operating profit was –S$3,654.87. Interest of S$450.43 takes it to the net loss. Net margin was –3.0%.
> - **Cash basis looks much better.** Sales received were S$196,407.51 and net cash flow was +S$63,970.03. That is about collecting money, not about earning it.
>
> **Why cash and profit differ:**
> - Cash received in September is higher than the sales invoiced in the month (S$136,528.55 accrual revenue; invoiced sales S$148,816.13 including the Orchid Bay and Kallang invoices). Part of it is likely older invoices being paid.
> - Receivables are still S$186,593.99 at month-end. Most of that is Bayfront Grocers, including INV-1057 for S$45,783.49, which was due 2026-09-19.
> - Stock rose, which tied up cash. Unpaid supplier bills (S$159,271.06 payables) also held back cash going out, so cash looks better than the real position.
>
> **Watch:**
> - Bayfront is 67.6% of September invoiced sales.
> - Meridian Food Imports is 89.6% of supplier bills.
> - The 3-month average net cash flow is –S$5,439.99 a month, so the business is burning cash. Runway is 28.8 months.
>
> The statement also counts 10 uncategorised payments as operating costs. Sorting out what they were could change the profit figure.
>
> I can go through the overdue Bayfront invoices or look at the trend over recent months if you'd like.

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
| biz-straits | yes | 2 | `727245cacd105a10c73079fe9e7bf590cde9f33c8899e1bd412768d64aabf03c` |

Claude usage for this case: 2 calls, about US$0.030.
