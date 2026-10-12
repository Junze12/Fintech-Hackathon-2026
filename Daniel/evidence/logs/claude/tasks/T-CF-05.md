# T-CF-05: What if the biggest customer pays three weeks late?

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** What-if runs on a copy of the forecast. The answer must give the new low point, and nothing real changes.

## Conversation

### Turn 1

**User:**

> What if Bayfront pays 3 weeks late?

*Assistant (before calling tools):*

> I need Bayfront's customer ID, so I'll look up the open invoices.

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
      "balance": "-13260.76",
      "week": 13
    },
    "scenario_low": {
      "date": "2026-11-14",
      "balance": "-70895.36",
      "week": 7
    },
    "low_point_change": "-57634.60",
    "base_first_below_zero": "2026-11-05",
    "scenario_first_below_zero": "2026-11-05",
    "base_end_balance": "-13260.76",
    "scenario_end_balance": "-52870.12",
    "weeks": [
      {
        "week": 1,
        "start": "2026-09-28",
        "end": "2026-10-04",
        "base_end_balance": "71006.16",
        "scenario_end_balance": "71006.16",
        "difference": "0.00"
      },
      {
        "week": 2,
        "start": "2026-10-05",
        "end": "2026-10-11",
        "base_end_balance": "119662.42",
        "scenario_end_balance": "73878.93",
        "difference": "-45783.49"
      },
      {
        "week": 3,
        "start": "2026-10-12",
        "end": "2026-10-18",
        "base_end_balance": "109744.38",
        "scenario_end_balance": "63960.89",
        "difference": "-45783.49"
      },
      {
        "week": 4,
        "start": "2026-10-19",
        "end": "2026-10-25",
        "base_end_balance": "116150.85",
        "scenario_end_balance": "70367.36",
        "difference": "-45783.49"
      },
      {
        "week": 5,
        "start": "2026-10-26",
        "end": "2026-11-01",
        "base_end_balance": "134844.92",
        "scenario_end_balance": "85560.96",
        "difference": "-49283.96"
      },
      {
        "week": 6,
        "start": "2026-11-02",
        "end": "2026-11-08",
        "base_end_balance": "-9611.40",
        "scenario_end_balance": "-58895.36",
        "difference": "-49283.96"
      },
      {
        "week": 7,
        "start": "2026-11-09",
        "end": "2026-11-15",
        "base_end_balance": "29671.80",
        "scenario_end_balance": "-70895.36",
        "difference": "-100567.16"
      },
      {
        "week": 8,
        "start": "2026-11-16",
        "end": "2026-11-22",
        "base_end_balance": "33960.23",
        "scenario_end_balance": "-17322.97",
        "difference": "-51283.20"
      },
      {
        "week": 9,
        "start": "2026-11-23",
        "end": "2026-11-29",
        "base_end_balance": "66030.16",
        "scenario_end_balance": "-24862.40",
        "difference": "-90892.56"
      },
      {
        "week": 10,
        "start": "2026-11-30",
        "end": "2026-12-06",
        "base_end_balance": "-5926.16",
        "scenario_end_balance": "-45535.52",
        "difference": "-39609.36"
      },
      {
        "week": 11,
        "start": "2026-12-07",
        "end": "2026-12-13",
        "base_end_balance": "29483.20",
        "scenario_end_balance": "-49735.52",
        "difference": "-79218.72"
      },
      {
        "week": 12,
        "start": "2026-12-14",
        "end": "2026-12-20",
        "base_end_balance": "14729.05",
        "scenario_end_balance": "-24880.31",
        "difference": "-39609.36"
      },
      {
        "week": 13,
        "start": "2026-12-21",
        "end": "2026-12-27",
        "base_end_balance": "-13260.76",
        "scenario_end_balance": "-52870.12",
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
    "scenario_gaps": [
      {
        "start": "2026-11-05",
        "end": "2026-11-30",
        "lowest_date": "2026-11-14",
        "lowest_balance": "-70895.36",
        "shortfall": "70895.36"
      },
      {
        "start": "2026-12-06",
        "end": "2026-12-27",
        "lowest_date": "2026-12-14",
        "lowest_balance": "-57535.52",
        "shortfall": "57535.52"
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
            "lowest_balance": "-9611.40",
            "shortfall": "9611.40"
          }
        ],
        "after": {
          "start": "2026-11-05",
          "end": "2026-11-30",
          "lowest_date": "2026-11-14",
          "lowest_balance": "-70895.36",
          "shortfall": "70895.36"
        },
        "worse": true
      },
      {
        "before": [
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
        "after": {
          "start": "2026-12-06",
          "end": "2026-12-27",
          "lowest_date": "2026-12-14",
          "lowest_balance": "-57535.52",
          "shortfall": "57535.52"
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

> If Bayfront pays 3 weeks late, the cash low point falls from S$-13,260.76 to S$-70,895.36 (a change of S$-57,634.60). The new low would fall on 14 Nov, in week 7, instead of 27 Dec.
>
> **What changes**
> - The forecast already goes below zero on 5 Nov without any delay. A late Bayfront payment makes that gap much deeper and longer. It would run from 5 Nov to 30 Nov, and the base forecast has it ending by 9 Nov.
> - A second gap would run from 6 Dec to 27 Dec. Its low point is S$-57,535.52, compared with S$-10,126.16 in the base forecast.
> - The forecast ends the 13 weeks at S$-52,870.12, compared with S$-13,260.76 in the base case.
> - The first three weeks are unaffected. The first impact is in week 2.
>
> **Invoices that slip by 21 days**
> - INV-1057, S$45,783.49, moves from 11 Oct to 1 Nov. It is already past its 19 Sep due date.
> - INV-1061, S$49,283.96, moves from 26 Oct to 16 Nov.
> - INV-1062, S$51,283.20, moves from 10 Nov to 1 Dec.
> - Two expected future Bayfront invoices, S$39,609.36 each, also move later. The second one drops out of the 13-week window.
>
> This is a simulation only, and nothing has been changed.
>
> Even on time, the forecast goes negative in November. I can look at ways to close the gap, such as chasing INV-1057 now, delaying supplier bills or financing. Would you like that?

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
| biz-straits | yes | 2 | `a599a67f408c69852b739e241fefc93022c8e26b9b01d4103adafd65cda08e0e` |

Claude usage for this case: 3 calls, about US$0.025.
