# T-CF-06: How do I fix the cash gap?

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

★ Demo video storyline, step 2 of 4.

**Why this case:** Non-borrowing options come first (chase invoice INV-1062), then the amount still to borrow.

## Conversation

### Turn 1

**User:**

> How do I fix the cash gap?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `recommend_actions` |  | **ok** | ok |
| `get_alerts` |  | **ok** | ok |

<details><summary>Tool result data</summary>

`recommend_actions`

```json
{
  "value": {
    "target": "0",
    "gaps": [
      {
        "start": "2026-11-05",
        "end": "2026-11-09",
        "lowest_date": "2026-11-05",
        "lowest_balance": "-9611.40",
        "shortfall": "9611.40"
      },
      {
        "start": "2026-12-06",
        "end": "2026-12-10",
        "lowest_date": "2026-12-10",
        "lowest_balance": "-10126.16",
        "shortfall": "10126.16"
      },
      {
        "start": "2026-12-27",
        "end": "2026-12-27",
        "lowest_date": "2026-12-27",
        "lowest_balance": "-13260.76",
        "shortfall": "13260.76"
      }
    ],
    "options": [
      {
        "rank": 1,
        "kind": "collect",
        "title": "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>",
        "changes": [
          {
            "kind": "collect_on_time",
            "invoice_id": "i-0062"
          }
        ],
        "amount": "51283.20",
        "effect": {
          "low_before": "-13260.76",
          "low_after": "-13260.76",
          "gaps_before": 3,
          "gaps_after": 2,
          "days_below_before": 11,
          "days_below_after": 6,
          "closes": [
            "2026-11-05"
          ]
        },
        "assumption": "Assumes the customer pays by the due date once reminded; they have usually paid later.",
        "follow_up_tool": "draft_reminder",
        "in_plan": true
      },
      {
        "rank": 2,
        "kind": "reschedule",
        "title": "<untrusted>Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19</untrusted>",
        "changes": [
          {
            "kind": "delay_payment",
            "bill_id": "b-bulk-stock",
            "days": 14
          }
        ],
        "amount": "-85000.00",
        "effect": {
          "low_before": "-13260.76",
          "low_after": "-13260.76",
          "gaps_before": 3,
          "gaps_after": 2,
          "days_below_before": 11,
          "days_below_after": 6,
          "closes": [
            "2026-11-05"
          ]
        },
        "assumption": "Needs the supplier's agreement; a late payment may cost a fee or an early-payment discount.",
        "follow_up_tool": null,
        "in_plan": false
      }
    ],
    "plan_effect": {
      "low_before": "-13260.76",
      "low_after": "-13260.76",
      "gaps_before": 3,
      "gaps_after": 2,
      "days_below_before": 11,
      "days_below_after": 6,
      "closes": [
        "2026-11-05"
      ]
    },
    "gaps_after_plan": [
      {
        "start": "2026-12-06",
        "end": "2026-12-10",
        "lowest_date": "2026-12-10",
        "lowest_balance": "-10126.16",
        "shortfall": "10126.16"
      },
      {
        "start": "2026-12-27",
        "end": "2026-12-27",
        "lowest_date": "2026-12-27",
        "lowest_balance": "-13260.76",
        "shortfall": "13260.76"
      }
    ],
    "borrowing_needed": true,
    "funding_need": {
      "amount": "13260.76",
      "target": "0",
      "draw_date": "2026-12-06",
      "repay_date": null,
      "duration_days": 22,
      "duration_months": 1,
      "duration_is_lower_bound": true,
      "purpose": "working capital: forecast cash gap",
      "basis": "after non-borrowing plan"
    },
    "need_without_actions": {
      "amount": "13260.76",
      "target": "0",
      "draw_date": "2026-11-05",
      "repay_date": null,
      "duration_days": 53,
      "duration_months": 2,
      "duration_is_lower_bound": true,
      "purpose": "working capital: forecast cash gap",
      "basis": "no action"
    },
    "message": "<untrusted>The steps without borrowing (Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10) close 1 of 3 gap(s), but not all. The rest needs about S$13,260.76 from 2026-12-06 for at least 22 days (cash hasn't recovered by the end of the forecast).</untrusted>"
  },
  "drivers": [
    {
      "label": "<untrusted>Gap from 2026-11-05 to 2026-11-09</untrusted>",
      "amount": "-9611.40",
      "detail": "<untrusted></untrusted>"
    },
    {
      "label": "<untrusted>Gap from 2026-12-06 to 2026-12-10</untrusted>",
      "amount": "-10126.16",
      "detail": "<untrusted></untrusted>"
    },
    {
      "label": "<untrusted>Gap from 2026-12-27 to 2026-12-27</untrusted>",
      "amount": "-13260.76",
      "detail": "<untrusted></untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2025-10-01",
    "period_end": "2026-09-30",
    "record_count": 206
  },
  "warnings": [
    "Cash is still below S$0.00 at the end of the forecast (2026-12-27), so the borrowing period is a minimum."
  ]
}
```

`get_alerts`

```json
{
  "floor": "68771.18",
  "floor_source": "default",
  "alerts": {
    "value": [
      {
        "key": "<untrusted>threshold</untrusted>",
        "kind": "threshold",
        "severity": "critical",
        "title": "<untrusted>Cash below your floor of S$68,771.18</untrusted>",
        "message": "<untrusted>Cash is forecast to fall below your floor of S$68,771.18 from 2026-11-05 (week 6), reaching -S$13,260.76 on 2026-12-27 - the account would be overdrawn.</untrusted>",
        "impact": "82031.94",
        "event_date": "2026-11-05",
        "days_away": 36,
        "score": "15950.66",
        "drivers": [
          {
            "label": "<untrusted>Bill MFI-88120 to Meridian Food Imports Pte. Ltd. due 2026-11-05</untrusted>",
            "amount": "-85000.00",
            "detail": "<untrusted>2026-11-05 (open_bill)</untrusted>"
          },
          {
            "label": "<untrusted>Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-10-06</untrusted>",
            "amount": "-58512.92",
            "detail": "<untrusted>2026-11-05 (expected_bill)</untrusted>"
          },
          {
            "label": "<untrusted>Expected invoice from Kallang Corner Stores, issued around 2026-10-19</untrusted>",
            "amount": "11242.58",
            "detail": "<untrusted>2026-11-04 (expected_invoice)</untrusted>"
          },
          {
            "label": "<untrusted>Expected bill to Eastwind Packaging Supplies, issued around 2026-10-06</untrusted>",
            "amount": "-6709.87",
            "detail": "<untrusted>2026-11-05 (expected_bill)</untrusted>"
          },
          {
            "label": "<untrusted>Expected bill to Harbour Freight Lines, issued around 2026-10-20</untrusted>",
            "amount": "-4836.11",
            "detail": "<untrusted>2026-11-03 (expected_bill)</untrusted>"
          }
        ]
      },
      {
        "key": "<untrusted>shortfall:Bill MFI-88120 to Meridian Food Imports Pte. Ltd. due 2026-11-05</untrusted>",
        "kind": "shortfall",
        "severity": "critical",
        "title": "<untrusted>Can't cover Bill MFI-88120 to Meridian Food Imports Pte. Ltd. due 2026-11-05</untrusted>",
        "message": "<untrusted>Not enough cash for Bill MFI-88120 to Meridian Food Imports Pte. Ltd. due 2026-11-05 (S$85,000.00). The forecast balance goes below zero on 2026-11-05 and bottoms out at -S$9,611.40 on 2026-11-05.</untrusted>",
        "impact": "9611.40",
        "event_date": "2026-11-05",
        "days_away": 36,
        "score": "1868.88",
        "drivers": [
          {
            "label": "<untrusted>Bill MFI-88120 to Meridian Food Imports Pte. Ltd. due 2026-11-05</untrusted>",
            "amount": "-85000.00",
            "detail": "<untrusted>2026-11-05 (open_bill)</untrusted>"
          },
          {
            "label": "<untrusted>Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-10-06</untrusted>",
            "amount": "-58512.92",
            "detail": "<untrusted>2026-11-05 (expected_bill)</untrusted>"
          },
          {
            "label": "<untrusted>Expected bill to Eastwind Packaging Supplies, issued around 2026-10-06</untrusted>",
            "amount": "-6709.87",
            "detail": "<untrusted>2026-11-05 (expected_bill)</untrusted>"
          }
        ]
      },
      {
        "key": "<untrusted>shortfall:Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-11-06</untrusted>",
        "kind": "shortfall",
        "severity": "critical",
        "title": "<untrusted>Can't cover Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-11-06</untrusted>",
        "message": "<untrusted>Not enough cash for Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-11-06 (S$58,512.92). The forecast balance goes below zero on 2026-12-06 and bottoms out at -S$10,126.16 on 2026-12-10.</untrusted>",
        "impact": "10126.16",
        "event_date": "2026-12-06",
        "days_away": 67,
        "score": "1057.96",
        "drivers": [
          {
            "label": "<untrusted>Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-11-06</untrusted>",
            "amount": "-58512.92",
            "detail": "<untrusted>2026-12-06 (expected_bill)</untrusted>"
          },
          {
            "label": "<untrusted>Expected bill to Eastwind Packaging Supplies, issued around 2026-11-06</untrusted>",
            "amount": "-6709.87",
            "detail": "<untrusted>2026-12-06 (expected_bill)</untrusted>"
          },
          {
            "label": "<untrusted>loan repayment (monthly, around day 10)</untrusted>",
            "amount": "-4200.00",
            "detail": "<untrusted>2026-12-10 (recurring)</untrusted>"
          }
        ]
      },
      {
        "key": "<untrusted>shortfall:payroll (monthly, around day 27)</untrusted>",
        "kind": "shortfall",
        "severity": "critical",
        "title": "<untrusted>Can't cover payroll (monthly, around day 27)</untrusted>",
        "message": "<untrusted>Not enough cash for payroll (monthly, around day 27) (S$39,232.39). The forecast balance goes below zero on 2026-12-27 and bottoms out at -S$13,260.76 on 2026-12-27.</untrusted>",
        "impact": "13260.76",
        "event_date": "2026-12-27",
        "days_away": 88,
        "score": "1054.83",
        "drivers": [
          {
            "label": "<untrusted>payroll (monthly, around day 27)</untrusted>",
            "amount": "-39232.39",
            "detail": "<untrusted>2026-12-27 (recurring)</untrusted>"
          }
        ]
      },
      {
        "key": "<untrusted>overdue:i-0057</untrusted>",
        "kind": "overdue_receivable",
        "severity": "info",
        "title": "<untrusted>Invoice INV-1057 is 11 days overdue</untrusted>",
        "message": "<untrusted>Invoice INV-1057 to Bayfront Grocers Pte. Ltd.: S$45,783.49 was due on 2026-09-19 and is 11 days overdue. Bayfront Grocers Pte. Ltd. usually pays about 22 days late, so this is normal for them.</untrusted>",
        "impact": "45783.49",
        "event_date": "2026-09-19",
        "days_away": 0,
        "score": "45783.49",
        "drivers": []
      }
    ],
    "drivers": [
      {
        "label": "<untrusted>Bill MFI-88120 to Meridian Food Imports Pte. Ltd. due 2026-11-05</untrusted>",
        "amount": "-85000.00",
        "detail": "<untrusted>2026-11-05 (open_bill)</untrusted>"
      },
      {
        "label": "<untrusted>Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-10-06</untrusted>",
        "amount": "-58512.92",
        "detail": "<untrusted>2026-11-05 (expected_bill)</untrusted>"
      },
      {
        "label": "<untrusted>Expected invoice from Kallang Corner Stores, issued around 2026-10-19</untrusted>",
        "amount": "11242.58",
        "detail": "<untrusted>2026-11-04 (expected_invoice)</untrusted>"
      },
      {
        "label": "<untrusted>Expected bill to Eastwind Packaging Supplies, issued around 2026-10-06</untrusted>",
        "amount": "-6709.87",
        "detail": "<untrusted>2026-11-05 (expected_bill)</untrusted>"
      },
      {
        "label": "<untrusted>Expected bill to Harbour Freight Lines, issued around 2026-10-20</untrusted>",
        "amount": "-4836.11",
        "detail": "<untrusted>2026-11-03 (expected_bill)</untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2025-10-01",
      "period_end": "2026-09-30",
      "record_count": 206
    },
    "warnings": []
  }
}
```

</details>

**Assistant:**

> **Short answer:** Collecting faster closes only one of the three forecast gaps. You would still need about S$13,260.76 of short-term borrowing.
>
> **The gaps (forecast, cash below zero):**
> - 5–9 Nov: low of -S$9,611.40. The S$85,000.00 Meridian bill MFI-88120 is due 5 Nov, together with an expected Meridian bill of S$58,512.92.
> - 6–10 Dec: low of -S$10,126.16. This is the next expected Meridian bill.
> - 27 Dec: low of -S$13,260.76. This is the S$39,232.39 payroll.
>
> **Steps that don't need borrowing:**
> 1. **Chase Bayfront Grocers invoice INV-1062 (S$51,283.20).** The aim is payment by 19 Oct instead of about 10 Nov. This closes the November gap.
>    - Bayfront usually pays about 22 days late, so this is uncertain.
>    - Bayfront's INV-1057 (S$45,783.49) is also 11 days overdue. That is normal for them, but it's worth chasing too.
> 2. **Ask Meridian to move bill MFI-88120 back 14 days, to 19 Nov.** This also closes the November gap. It needs the supplier's agreement, and there may be a late fee.
>
> Each step closes the November gap, and neither fixes December. The tool shows the plan reducing the gaps from 3 to 2.
>
> **Borrowing:** After step 1, about S$13,260.76 would be needed from 6 Dec for at least 22 days. Cash doesn't recover by the end of the forecast, so the real period may be longer.
>
> Cash is also forecast to fall below your default floor of S$68,771.18 from 5 Nov.
>
> Next steps I can take:
> - Draft a reminder to Bayfront.
> - Look at financing options, with total cost and effective annual rate (EIR).
> - Run a what-if, for example both steps together or pausing some spending.
>
> Which would you like?

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 2.

None: no write was attempted.

## Sandbox bank operations

None: the sandbox bank was not asked to move or record any money.

**Balances:**

| Account | Before | After | Change |
|---|---|---|---|
| Operating account ••••8886 | S$148,161.41 | S$148,161.41 | S$0.00 |
| Reserve account ••••1570 | S$5,000.00 | S$5,000.00 | S$0.00 |

## Audit hash chain

| Business | Verified | Entries | Head hash |
|---|---|---|---|
| biz-straits | yes | 2 | `2c009f16e65b49def953a3c91e8bd9e5694ae12902eed2ea1a60270ce3712b59` |

Claude usage for this case: 2 calls, about US$0.025.
