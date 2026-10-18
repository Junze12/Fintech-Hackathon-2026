# T-AN-06: Who owes us money and who pays late

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Receivables ageing plus each customer's habit. Straits Harbour has one overdue invoice (INV-1057, Bayfront, 11 days late) and Orchid Bay pays slowest on average.

## Conversation

### Turn 1

**User:**

> Who owes us money, and which customers pay late?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_ageing` |  | **ok** | ok |

<details><summary>Tool result data</summary>

`get_ageing`

```json
{
  "receivables": {
    "value": {
      "as_of": "2026-09-30",
      "kind": "receivables",
      "basis": "invoice",
      "total": "186593.99",
      "overdue": "45783.49",
      "overdue_share": "0.2454",
      "buckets": [
        {
          "bucket": "not_due",
          "label": "Not yet due",
          "amount": "140810.50",
          "count": 4
        },
        {
          "bucket": "1_30",
          "label": "1-30 days overdue",
          "amount": "45783.49",
          "count": 1
        },
        {
          "bucket": "31_60",
          "label": "31-60 days overdue",
          "amount": "0",
          "count": 0
        },
        {
          "bucket": "61_90",
          "label": "61-90 days overdue",
          "amount": "0",
          "count": 0
        },
        {
          "bucket": "over_90",
          "label": "Over 90 days overdue",
          "amount": "0",
          "count": 0
        }
      ],
      "oldest_overdue": [
        {
          "id": "i-0057",
          "number": "<untrusted>INV-1057</untrusted>",
          "counterparty_id": "c-bayfront",
          "counterparty_name": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
          "due_date": "2026-09-19",
          "days_overdue": 11,
          "outstanding": "45783.49"
        }
      ],
      "customers": [
        {
          "customer_id": "c-orchid",
          "name": "<untrusted>Orchid Bay Hospitality</untrusted>",
          "avg_days_late": "23.6",
          "paid_invoices_matched": 12,
          "outstanding": "27914.76",
          "overdue": "0",
          "paid_by_due_pct": "0.0"
        },
        {
          "customer_id": "c-bayfront",
          "name": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
          "avg_days_late": "22.5",
          "paid_invoices_matched": 24,
          "outstanding": "146350.65",
          "overdue": "45783.49",
          "paid_by_due_pct": "0.0"
        },
        {
          "customer_id": "c-kallang",
          "name": "<untrusted>Kallang Corner Stores</untrusted>",
          "avg_days_late": "2.3",
          "paid_invoices_matched": 24,
          "outstanding": "12328.58",
          "overdue": "0",
          "paid_by_due_pct": "25.0"
        }
      ]
    },
    "drivers": [
      {
        "label": "<untrusted>INV-1057 (Bayfront Grocers Pte. Ltd.)</untrusted>",
        "amount": "45783.49",
        "detail": "<untrusted>11 days overdue, due 2026-09-19</untrusted>"
      }
    ],
    "data_coverage": {
      "period_start": "2026-08-20",
      "period_end": "2026-09-30",
      "record_count": 5
    },
    "warnings": [
      "Invoice basis: built from unpaid invoices as of 2026-09-30, not from bank balances"
    ]
  },
  "payables": {
    "value": {
      "as_of": "2026-09-30",
      "kind": "payables",
      "basis": "invoice",
      "total": "159271.06",
      "overdue": "0.00",
      "overdue_share": "0.0000",
      "buckets": [
        {
          "bucket": "not_due",
          "label": "Not yet due",
          "amount": "159271.06",
          "count": 4
        },
        {
          "bucket": "1_30",
          "label": "1-30 days overdue",
          "amount": "0",
          "count": 0
        },
        {
          "bucket": "31_60",
          "label": "31-60 days overdue",
          "amount": "0",
          "count": 0
        },
        {
          "bucket": "61_90",
          "label": "61-90 days overdue",
          "amount": "0",
          "count": 0
        },
        {
          "bucket": "over_90",
          "label": "Over 90 days overdue",
          "amount": "0",
          "count": 0
        }
      ],
      "oldest_overdue": [],
      "customers": []
    },
    "drivers": [],
    "data_coverage": {
      "period_start": "2026-09-03",
      "period_end": "2026-09-30",
      "record_count": 4
    },
    "warnings": [
      "Invoice basis: built from unpaid bills as of 2026-09-30, not from bank balances"
    ]
  }
}
```

</details>

**Assistant:**

> Customers owe us S$186,593.99 in total (invoice basis). Of that, S$45,783.49 is overdue (24.54%) and S$140,810.50 is not yet due.
>
> **Who owes us**
> - **Bayfront Grocers Pte. Ltd.** owes S$146,350.65. Of that, S$45,783.49 is overdue. That is INV-1057, due 2026-09-19 and 11 days late.
> - **Orchid Bay Hospitality** owes S$27,914.76. None of it is overdue yet.
> - **Kallang Corner Stores** owes S$12,328.58. None of it is overdue.
>
> **Who pays late (average days after the due date)**
> - **Orchid Bay Hospitality** pays 23.6 days late on average. None of its 12 matched paid invoices was paid by the due date.
> - **Bayfront Grocers** pays 22.5 days late on average. None of its 24 matched paid invoices was paid by the due date. It is also our biggest exposure.
> - **Kallang Corner Stores** pays 2.3 days late on average. It paid 25% of its 24 matched invoices by the due date.
>
> Bayfront's overdue invoice is still within its usual lateness. I can draft a payment reminder for INV-1057 if you want one.

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
| biz-straits | yes | 1 | `c6bae4401b81adf575a9edcee5ec29c36161948eed43e5592e08061b05b845d1` |

Claude usage for this case: 2 calls, about US$0.021.
