# T-CF-05: What if the biggest customer pays three weeks late?

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** What-if runs on a copy of the forecast. The answer must give the new low point, and nothing real changes.

## Conversation

### Turn 1

**User:**

> What if Bayfront pays 3 weeks late?

*Assistant (before calling tools):*

> I need Bayfront's customer or invoice ids first, so I'll look up the open invoices.

*Assistant (before calling tools):*

> Bayfront has three open invoices, so I'll apply the 21-day delay to the customer as a whole.

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `list_invoices` |  | **ok** | ok |
| `run_what_if` | {"changes": [{"kind": "delay_receipt", "customer_id": "c-bayfront", "days": 21}]} | **ok** | ok |

<details><summary>Tool result data</summary>

`list_invoices`

```json
[
  {
    "id": "i-0057",
    "number": "<untrusted>INV-1057</untrusted>",
    "counterparty_id": "c-bayfront",
    "counterparty_name": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
    "issue_date": "2026-08-20",
    "due_date": "2026-09-19",
    "amount": "45783.49",
    "outstanding": "45783.49",
    "status": "open",
    "notes": null
  },
  {
    "id": "i-0065",
    "number": "<untrusted>INV-1065</untrusted>",
    "counterparty_id": "c-kallang",
    "counterparty_name": "<untrusted>Kallang Corner Stores</untrusted>",
    "issue_date": "2026-09-19",
    "due_date": "2026-10-03",
    "amount": "12328.58",
    "outstanding": "12328.58",
    "status": "open",
    "notes": null
  },
  {
    "id": "i-0061",
    "number": "<untrusted>INV-1061</untrusted>",
    "counterparty_id": "c-bayfront",
    "counterparty_name": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
    "issue_date": "2026-09-04",
    "due_date": "2026-10-04",
    "amount": "49283.96",
    "outstanding": "49283.96",
    "status": "open",
    "notes": null
  },
  {
    "id": "i-0063",
    "number": "<untrusted>INV-1063</untrusted>",
    "counterparty_id": "c-orchid",
    "counterparty_name": "<untrusted>Orchid Bay Hospitality</untrusted>",
    "issue_date": "2026-09-07",
    "due_date": "2026-10-07",
    "amount": "27914.76",
    "outstanding": "27914.76",
    "status": "open",
    "notes": null
  },
  {
    "id": "i-0062",
    "number": "<untrusted>INV-1062</untrusted>",
    "counterparty_id": "c-bayfront",
    "counterparty_name": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
    "issue_date": "2026-09-19",
    "due_date": "2026-10-19",
    "amount": "51283.20",
    "outstanding": "51283.20",
    "status": "open",
    "notes": null
  }
]
```

`run_what_if`

```json
{
  "value": {
    "changes": [
      {
        "kind": "delay_receipt",
        "invoice_id": null,
        "customer_id": "c-bayfront",
        "days": 21
      }
    ],
    "base_low": {
      "date": "2026-12-27",
      "balance": "-13025.81",
      "week": 13
    },
    "scenario_low": {
      "date": "2026-11-14",
      "balance": "-70660.41",
      "week": 7
    },
    "low_point_change": "-57634.60",
    "base_first_below_zero": "2026-11-05",
    "scenario_first_below_zero": "2026-11-05",
    "base_end_balance": "-13025.81",
    "scenario_end_balance": "-52635.17",
    "weeks": [
      {
        "week": 1,
        "start": "2026-09-28",
        "end": "2026-10-04",
        "base_end_balance": "74371.60",
        "scenario_end_balance": "74371.60",
        "difference": "0.00"
      },
      {
        "week": 2,
        "start": "2026-10-05",
        "end": "2026-10-11",
        "base_end_balance": "123027.86",
        "scenario_end_balance": "77244.37",
        "difference": "-45783.49"
      },
      {
        "week": 3,
        "start": "2026-10-12",
        "end": "2026-10-18",
        "base_end_balance": "113109.82",
        "scenario_end_balance": "67326.33",
        "difference": "-45783.49"
      },
      {
        "week": 4,
        "start": "2026-10-19",
        "end": "2026-10-25",
        "base_end_balance": "119516.29",
        "scenario_end_balance": "73732.80",
        "difference": "-45783.49"
      },
      {
        "week": 5,
        "start": "2026-10-26",
        "end": "2026-11-01",
        "base_end_balance": "135079.87",
        "scenario_end_balance": "85795.91",
        "difference": "-49283.96"
      },
      {
        "week": 6,
        "start": "2026-11-02",
        "end": "2026-11-08",
        "base_end_balance": "-9376.45",
        "scenario_end_balance": "-58660.41",
        "difference": "-49283.96"
      },
      {
        "week": 7,
        "start": "2026-11-09",
        "end": "2026-11-15",
        "base_end_balance": "29906.75",
        "scenario_end_balance": "-70660.41",
        "difference": "-100567.16"
      },
      {
        "week": 8,
        "start": "2026-11-16",
        "end": "2026-11-22",
        "base_end_balance": "34195.18",
        "scenario_end_balance": "-17088.02",
        "difference": "-51283.20"
      },
      {
        "week": 9,
        "start": "2026-11-23",
        "end": "2026-11-29",
        "base_end_balance": "66265.11",
        "scenario_end_balance": "-24627.45",
        "difference": "-90892.56"
      },
      {
        "week": 10,
        "start": "2026-11-30",
        "end": "2026-12-06",
        "base_end_balance": "-5691.21",
        "scenario_end_balance": "-45300.57",
        "difference": "-39609.36"
      },
      {
        "week": 11,
        "start": "2026-12-07",
        "end": "2026-12-13",
        "base_end_balance": "29718.15",
        "scenario_end_balance": "-49500.57",
        "difference": "-79218.72"
      },
      {
        "week": 12,
        "start": "2026-12-14",
        "end": "2026-12-20",
        "base_end_balance": "14964.00",
        "scenario_end_balance": "-24645.36",
        "difference": "-39609.36"
      },
      {
        "week": 13,
        "start": "2026-12-21",
        "end": "2026-12-27",
        "base_end_balance": "-13025.81",
        "scenario_end_balance": "-52635.17",
        "difference": "-39609.36"
      }
    ],
    "week_runs": [
      {
        "first_week": 2,
        "last_week": 4,
        "start": "2026-10-05",
        "end": "2026-10-25",
        "difference": "-45783.49"
      },
      {
        "first_week": 5,
        "last_week": 6,
        "start": "2026-10-26",
        "end": "2026-11-08",
        "difference": "-49283.96"
      },
      {
        "first_week": 7,
        "last_week": 7,
        "start": "2026-11-09",
        "end": "2026-11-15",
        "difference": "-100567.16"
      },
      {
        "first_week": 8,
        "last_week": 8,
        "start": "2026-11-16",
        "end": "2026-11-22",
        "difference": "-51283.20"
      },
      {
        "first_week": 9,
        "last_week": 9,
        "start": "2026-11-23",
        "end": "2026-11-29",
        "difference": "-90892.56"
      },
      {
        "first_week": 10,
        "last_week": 10,
        "start": "2026-11-30",
        "end": "2026-12-06",
        "difference": "-39609.36"
      },
      {
        "first_week": 11,
        "last_week": 11,
        "start": "2026-12-07",
        "end": "2026-12-13",
        "difference": "-79218.72"
      },
      {
        "first_week": 12,
        "last_week": 13,
        "start": "2026-12-14",
        "end": "2026-12-27",
        "difference": "-39609.36"
      }
    ],
    "base_gaps": [
      {
        "start": "2026-11-05",
        "end": "2026-11-09",
        "lowest_date": "2026-11-05",
        "lowest_balance": "-9376.45",
        "shortfall": "9376.45"
      },
      {
        "start": "2026-12-06",
        "end": "2026-12-10",
        "lowest_date": "2026-12-10",
        "lowest_balance": "-9891.21",
        "shortfall": "9891.21"
      },
      {
        "start": "2026-12-27",
        "end": "2026-12-27",
        "lowest_date": "2026-12-27",
        "lowest_balance": "-13025.81",
        "shortfall": "13025.81"
      }
    ],
    "scenario_gaps": [
      {
        "start": "2026-11-05",
        "end": "2026-11-30",
        "lowest_date": "2026-11-14",
        "lowest_balance": "-70660.41",
        "shortfall": "70660.41"
      },
      {
        "start": "2026-12-06",
        "end": "2026-12-27",
        "lowest_date": "2026-12-14",
        "lowest_balance": "-57300.57",
        "shortfall": "57300.57"
      }
    ],
    "gaps_closed": [],
    "gaps_new": [],
    "gaps_changed": [
      {
        "before": [
          {
            "start": "2026-11-05",
            "end": "2026-11-09",
            "lowest_date": "2026-11-05",
            "lowest_balance": "-9376.45",
            "shortfall": "9376.45"
          }
        ],
        "after": {
          "start": "2026-11-05",
          "end": "2026-11-30",
          "lowest_date": "2026-11-14",
          "lowest_balance": "-70660.41",
          "shortfall": "70660.41"
        },
        "worse": true
      },
      {
        "before": [
          {
            "start": "2026-12-06",
            "end": "2026-12-10",
            "lowest_date": "2026-12-10",
            "lowest_balance": "-9891.21",
            "shortfall": "9891.21"
          },
          {
            "start": "2026-12-27",
            "end": "2026-12-27",
            "lowest_date": "2026-12-27",
            "lowest_balance": "-13025.81",
            "shortfall": "13025.81"
          }
        ],
        "after": {
          "start": "2026-12-06",
          "end": "2026-12-27",
          "lowest_date": "2026-12-14",
          "lowest_balance": "-57300.57",
          "shortfall": "57300.57"
        },
        "worse": true
      }
    ],
    "timing_only": false,
    "changed_items": [
      {
        "label": "<untrusted>Invoice INV-1057 from Bayfront Grocers Pte. Ltd. (due 2026-09-19)</untrusted>",
        "amount": "45783.49",
        "from_date": "2026-10-11",
        "to_date": "2026-11-01"
      },
      {
        "label": "<untrusted>Invoice INV-1061 from Bayfront Grocers Pte. Ltd. (due 2026-10-04)</untrusted>",
        "amount": "49283.96",
        "from_date": "2026-10-26",
        "to_date": "2026-11-16"
      },
      {
        "label": "<untrusted>Invoice INV-1062 from Bayfront Grocers Pte. Ltd. (due 2026-10-19)</untrusted>",
        "amount": "51283.20",
        "from_date": "2026-11-10",
        "to_date": "2026-12-01"
      },
      {
        "label": "<untrusted>Expected invoice from Bayfront Grocers Pte. Ltd., issued around 2026-10-06</untrusted>",
        "amount": "39609.36",
        "from_date": "2026-11-27",
        "to_date": "2026-12-18"
      },
      {
        "label": "<untrusted>Expected invoice from Bayfront Grocers Pte. Ltd., issued around 2026-10-20</untrusted>",
        "amount": "39609.36",
        "from_date": "2026-12-11",
        "to_date": null
      }
    ],
    "notes": [
      "<untrusted>Expected invoice from Bayfront Grocers Pte. Ltd., issued around 2026-10-20 moves past the end of the forecast (2026-12-27), so it drops out of the 13 weeks.</untrusted>",
      "<untrusted>Every payment from Bayfront Grocers Pte. Ltd. arrives 21 days later than expected.</untrusted>"
    ]
  },
  "drivers": [
    {
      "label": "<untrusted>Week 7 (2026-11-09 to 2026-11-15)</untrusted>",
      "amount": "-100567.16",
      "detail": "<untrusted></untrusted>"
    },
    {
      "label": "<untrusted>Week 9 (2026-11-23 to 2026-11-29)</untrusted>",
      "amount": "-90892.56",
      "detail": "<untrusted></untrusted>"
    },
    {
      "label": "<untrusted>Week 11 (2026-12-07 to 2026-12-13)</untrusted>",
      "amount": "-79218.72",
      "detail": "<untrusted></untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2025-10-01",
    "period_end": "2026-09-30",
    "record_count": 206
  },
  "warnings": []
}
```

</details>

**Assistant:**

> **A 3-week delay from Bayfront makes the cash gap much deeper. It also keeps cash below zero for most of November and December.** This is a temporary what-if and nothing is saved.
>
> I delayed every Bayfront payment by 21 days. That covers three open invoices (INV-1057, INV-1061 and INV-1062) and two invoices the forecast expects them to be issued.
>
> - **Lowest point:** cash falls to -S$70,660.41 on 2026-11-14. The current forecast's lowest point is -S$13,025.81 on 2026-12-27, so the change is -S$57,634.60.
> - **First day below zero:** 2026-11-05 in both cases.
> - **Length of the gap:** the base forecast has short dips, the first of them 2026-11-05 to 2026-11-09. With the delay, cash stays negative from 2026-11-05 to 2026-11-30. A second gap runs from 2026-12-06 to 2026-12-27, with a low of -S$57,300.57.
> - **End of the 13 weeks:** the balance is -S$52,635.17, against -S$13,025.81 in the base forecast.
>
> **Payments that move:**
> - INV-1057 (S$45,783.49) moves from 2026-10-11 to 2026-11-01.
> - INV-1061 (S$49,283.96) moves from 2026-10-26 to 2026-11-16.
> - INV-1062 (S$51,283.20) moves from 2026-11-10 to 2026-12-01.
>
> Your forecast is already short in early November without any delay. Bayfront paying late would make that gap much larger.
>
> I can look at ways to cover it, such as chasing INV-1057, which is already past its due date. I can also run recommended actions or a stress test. Tell me which you'd like.

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
| biz-straits | yes | 2 | `063a75f5d90eabd5ef4048dbaf24f56dd1ecfc480314e0a6d2181c78acd2d701` |

Claude usage for this case: 3 calls, about US$0.036.
