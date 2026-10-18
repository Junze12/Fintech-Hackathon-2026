# T-AN-05: Dependence on the biggest customer

**Result: PASS**  ·  suite: tasks  ·  scenario: `concentrated_b2b`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Clearpath gets about 61% of its invoiced sales from Tidewater. The answer must name the customer and give the share for the period asked.

## Conversation

### Turn 1

**User:**

> Over the last 12 months, how dependent are we on our biggest customer?

*Assistant (before calling tools):*

> Last 12 months: 2025-10-01 to 2026-09-30.

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_metrics` | {"start": "2025-10-01", "end": "2026-09-30"} | **ok** | ok |

<details><summary>Tool result data</summary>

`get_metrics`

```json
{
  "period": {
    "value": {
      "start": "2025-10-01",
      "end": "2026-09-30",
      "basis": "cash",
      "revenue": "1302855.73",
      "cogs": "240429.68",
      "opex": "867679.11",
      "gross_margin": "0.8155",
      "operating_margin": "0.1495",
      "net_cash_flow": "104994.50",
      "uncategorised_count": 9,
      "uncategorised_net": "-2210.40"
    },
    "drivers": [
      {
        "label": "<untrusted>Revenue (sales received)</untrusted>",
        "amount": "1302855.73",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Cost of goods sold</untrusted>",
        "amount": "-240429.68",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Operating expenses</untrusted>",
        "amount": "-867679.11",
        "detail": "<untrusted></untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2025-10-01",
      "period_end": "2026-09-30",
      "record_count": 193
    },
    "warnings": [
      "Cash basis: revenue and costs are counted when money moves, not when invoiced",
      "9 uncategorised transactions (net -S$2,210.40) are excluded from revenue and costs"
    ]
  },
  "accrual": {
    "basis": "accrual",
    "revenue": "1185771.34",
    "gross_margin": "0.8195",
    "operating_margin": "0.0618",
    "net_margin": "0.0618",
    "net_profit": "73321.67",
    "adjustments_included": 0
  },
  "working_capital": {
    "value": {
      "start": "2025-10-01",
      "end": "2026-09-30",
      "basis": "invoice",
      "days": 365,
      "invoiced_sales": "1292490.77",
      "receivables": "101998.32",
      "dso": "28.8",
      "bills_received": "233325.58",
      "payables": "15379.78",
      "dpo": "24.1",
      "ccc": "4.7",
      "cash": "194994.50",
      "net_working_capital": "281613.04"
    },
    "drivers": [
      {
        "label": "<untrusted>Receivables at period end</untrusted>",
        "amount": "101998.32",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Payables at period end</untrusted>",
        "amount": "-15379.78",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Unpaid invoice INV-1049</untrusted>",
        "amount": "54483.18",
        "detail": "<untrusted>Tidewater Port Logistics Pte. Ltd., due 2026-10-05</untrusted>"
      },
      {
        "label": "<untrusted>Unpaid invoice INV-1048</untrusted>",
        "amount": "16942.52",
        "detail": "<untrusted>Lumen Home Retail, due 2026-09-05</untrusted>"
      },
      {
        "label": "<untrusted>Unpaid invoice INV-1052</untrusted>",
        "amount": "15791.36",
        "detail": "<untrusted>Lumen Home Retail, due 2026-10-04</untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2025-10-01",
      "period_end": "2026-09-30",
      "record_count": 78
    },
    "warnings": [
      "Invoice basis: receivables, payables and their days use invoices and bills, not bank receipts",
      "DIO omitted: there is no inventory data, so the cash conversion cycle is DSO - DPO",
      "Net working capital = cash at period end + receivables - payables; no inventory or other short-term debt is in the data"
    ]
  },
  "concentration": {
    "value": {
      "start": "2025-10-01",
      "end": "2026-09-30",
      "basis": "invoice",
      "total_invoiced": "1292490.77",
      "largest": {
        "customer_id": "c-tidewater",
        "name": "<untrusted>Tidewater Port Logistics Pte. Ltd.</untrusted>",
        "invoiced": "791146.73",
        "share": "0.6121"
      },
      "customers": [
        {
          "customer_id": "c-tidewater",
          "name": "<untrusted>Tidewater Port Logistics Pte. Ltd.</untrusted>",
          "invoiced": "791146.73",
          "share": "0.6121"
        },
        {
          "customer_id": "c-northshore",
          "name": "<untrusted>Northshore Medical Group</untrusted>",
          "invoiced": "201233.84",
          "share": "0.1557"
        },
        {
          "customer_id": "c-lumen",
          "name": "<untrusted>Lumen Home Retail</untrusted>",
          "invoiced": "154008.28",
          "share": "0.1192"
        },
        {
          "customer_id": "c-pinewood",
          "name": "<untrusted>Pinewood Learning Centre</untrusted>",
          "invoiced": "146101.92",
          "share": "0.1130"
        }
      ]
    },
    "drivers": [
      {
        "label": "<untrusted>Tidewater Port Logistics Pte. Ltd.</untrusted>",
        "amount": "791146.73",
        "detail": "<untrusted>61.2% of invoiced sales</untrusted>"
      },
      {
        "label": "<untrusted>Northshore Medical Group</untrusted>",
        "amount": "201233.84",
        "detail": "<untrusted>15.6% of invoiced sales</untrusted>"
      },
      {
        "label": "<untrusted>Lumen Home Retail</untrusted>",
        "amount": "154008.28",
        "detail": "<untrusted>11.9% of invoiced sales</untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2025-10-01",
      "period_end": "2026-09-30",
      "record_count": 48
    },
    "warnings": [
      "Invoice basis: shares use invoices issued in the period, not bank receipts",
      "One customer accounts for more than 50% of invoiced sales; losing or delaying them would hit cash hard"
    ]
  },
  "supplier_concentration": {
    "value": {
      "start": "2025-10-01",
      "end": "2026-09-30",
      "basis": "invoice",
      "total_billed": "233325.58",
      "largest": {
        "supplier_id": "s-northpoint",
        "name": "<untrusted>Northpoint Contract Engineers</untrusted>",
        "billed": "182600.63",
        "share": "0.7826"
      },
      "suppliers": [
        {
          "supplier_id": "s-northpoint",
          "name": "<untrusted>Northpoint Contract Engineers</untrusted>",
          "billed": "182600.63",
          "share": "0.7826"
        },
        {
          "supplier_id": "s-stratus",
          "name": "<untrusted>Stratus Hosting Asia</untrusted>",
          "billed": "50724.95",
          "share": "0.2174"
        }
      ]
    },
    "drivers": [
      {
        "label": "<untrusted>Northpoint Contract Engineers</untrusted>",
        "amount": "182600.63",
        "detail": "<untrusted>78.3% of supplier bills</untrusted>"
      },
      {
        "label": "<untrusted>Stratus Hosting Asia</untrusted>",
        "amount": "50724.95",
        "detail": "<untrusted>21.7% of supplier bills</untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2025-10-01",
      "period_end": "2026-09-30",
      "record_count": 24
    },
    "warnings": [
      "Invoice basis: shares use supplier bills issued in the period, not payments",
      "One supplier accounts for more than 50% of purchases; a price rise or delivery problem there would hit the business hard"
    ]
  },
  "runway": {
    "value": {
      "as_of": "2026-09-30",
      "cash": "194994.50",
      "avg_monthly_net_flow": "12424.83",
      "months": null,
      "status": "cash-flow positive"
    },
    "drivers": [
      {
        "label": "<untrusted>Cash across all accounts</untrusted>",
        "amount": "194994.50",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Average monthly net cash flow, last 3 months</untrusted>",
        "amount": "12424.83",
        "detail": "<untrusted></untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2026-07-01",
      "period_end": "2026-09-30",
      "record_count": 51
    },
    "warnings": []
  }
}
```

</details>

**Assistant:**

> We depend heavily on one customer. Over the last 12 months (1 Oct 2025 to 30 Sep 2026, invoice basis), Tidewater Port Logistics Pte. Ltd. made up 61.21% of invoiced sales. That is S$791,146.73 of S$1,292,490.77.
>
> The other customers are much smaller:
> - Northshore Medical Group: 15.57%
> - Lumen Home Retail: 11.92%
> - Pinewood Learning Centre: 11.30%
>
> Tidewater also has the largest unpaid invoice. INV-1049 is S$54,483.18, due 5 Oct 2026. Total receivables are S$101,998.32.
>
> If Tidewater paid late or left, cash would take a big hit. You are cash-flow positive at the moment. Cash is S$194,994.50, and average net cash flow over the last 3 months is S$12,424.83 a month.
>
> I can run a what-if, for example Tidewater paying several weeks late, to see what it would do to cash.

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 1.

None: no write was attempted.

## Sandbox bank operations

None: the sandbox bank was not asked to move or record any money.

**Balances:**

| Account | Before | After | Change |
|---|---|---|---|
| Operating account ••••6943 | S$104,994.50 | S$104,994.50 | S$0.00 |
| Reserve account ••••1490 | S$90,000.00 | S$90,000.00 | S$0.00 |

## Audit hash chain

| Business | Verified | Entries | Head hash |
|---|---|---|---|
| biz-clearpath | yes | 1 | `710604bef9b903b9a25ffbb41c09e78e220e262bc07cbe717400e7ed0f2b03e5` |

Claude usage for this case: 2 calls, about US$0.024.
