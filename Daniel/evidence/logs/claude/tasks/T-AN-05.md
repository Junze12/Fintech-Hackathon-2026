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
      "net_cash_flow": "171591.05",
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
      "ccc": "4.7"
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
      "DIO omitted: there is no inventory data, so the cash conversion cycle is DSO - DPO"
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
  "runway": {
    "value": {
      "as_of": "2026-09-30",
      "cash": "261591.05",
      "avg_monthly_net_flow": "18324.90",
      "months": null,
      "status": "cash-flow positive"
    },
    "drivers": [
      {
        "label": "<untrusted>Cash across all accounts</untrusted>",
        "amount": "261591.05",
        "detail": "<untrusted></untrusted>"
      },
      {
        "label": "<untrusted>Average monthly net cash flow, last 3 months</untrusted>",
        "amount": "18324.90",
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

> You depend heavily on one customer. Tidewater Port Logistics Pte. Ltd. accounts for 61.21% of invoiced sales over the last 12 months (2025-10-01 to 2026-09-30). That is S$791,146.73 of S$1,292,490.77 total. These figures use the invoice basis.
>
> The other customers are much smaller:
> - Northshore Medical Group: 15.57%
> - Lumen Home Retail: 11.92%
> - Pinewood Learning Centre: 11.30%
>
> **Why it matters:** if Tidewater paid late or left, your cash would take a big hit. Tidewater invoice INV-1049 for S$54,483.18 is due 2026-10-05 and is currently unpaid. It is the largest open receivable.
>
> **Cushion:** you have S$261,591.05 in cash and are cash-flow positive. Average net cash flow over the last 3 months is S$18,324.90 a month.
>
> I can run a what-if, for example Tidewater paying several weeks late, to see how far cash would fall.

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 1.

None: no write was attempted.

## Sandbox bank operations

None: the sandbox bank was not asked to move or record any money.

**Balances:**

| Account | Before | After | Change |
|---|---|---|---|
| Operating account ••••6943 | S$171,591.05 | S$171,591.05 | S$0.00 |
| Reserve account ••••1490 | S$90,000.00 | S$90,000.00 | S$0.00 |

## Audit hash chain

| Business | Verified | Entries | Head hash |
|---|---|---|---|
| biz-clearpath | yes | 1 | `afe3aa1e3cfa4984095020440566fa5d50d66606d880dfcbb91c2d2b26308e19` |

Claude usage for this case: 2 calls, about US$0.016.
