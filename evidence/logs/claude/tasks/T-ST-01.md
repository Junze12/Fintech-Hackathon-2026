# T-ST-01: Chances of running out of cash

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** The 13-week forecast gives one path; the stress test simulates 2,000 runs of customer payment timing from each customer's own past delays. For Straits Harbour almost every run goes below zero, most often first on 5 Nov (the S$85,000 MFI-88120 bill), in about 84% of runs. The answer must give the likelihood from the simulation, name the day, and not present it as a certainty.

## Conversation

### Turn 1

**User:**

> What are the chances we run out of cash in the next three months?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `stress_test_cash` |  | **ok** | ok |
| `get_alerts` |  | **ok** | ok |

<details><summary>Tool result data</summary>

`stress_test_cash`

```json
{
  "value": {
    "as_of": "2026-09-30",
    "horizon_end": "2026-12-27",
    "runs": 2000,
    "seed": 20261020,
    "target_pct": 95,
    "floor": "0",
    "shock": {
      "amount": "0",
      "date": null
    },
    "shock_day_used": "2026-11-05",
    "survival_pct": "0.00",
    "survival_without_shock_pct": "0.00",
    "meets_target": false,
    "failures": {
      "runs_failing": 2000,
      "most_likely_day": "2026-11-05",
      "most_likely_day_share_pct": "83.70",
      "by_week": [
        {
          "week": 1,
          "start": "2026-09-28",
          "end": "2026-10-04",
          "runs": 0
        },
        {
          "week": 2,
          "start": "2026-10-05",
          "end": "2026-10-11",
          "runs": 0
        },
        {
          "week": 3,
          "start": "2026-10-12",
          "end": "2026-10-18",
          "runs": 0
        },
        {
          "week": 4,
          "start": "2026-10-19",
          "end": "2026-10-25",
          "runs": 0
        },
        {
          "week": 5,
          "start": "2026-10-26",
          "end": "2026-11-01",
          "runs": 0
        },
        {
          "week": 6,
          "start": "2026-11-02",
          "end": "2026-11-08",
          "runs": 1674
        },
        {
          "week": 7,
          "start": "2026-11-09",
          "end": "2026-11-15",
          "runs": 0
        },
        {
          "week": 8,
          "start": "2026-11-16",
          "end": "2026-11-22",
          "runs": 0
        },
        {
          "week": 9,
          "start": "2026-11-23",
          "end": "2026-11-29",
          "runs": 61
        },
        {
          "week": 10,
          "start": "2026-11-30",
          "end": "2026-12-06",
          "runs": 212
        },
        {
          "week": 11,
          "start": "2026-12-07",
          "end": "2026-12-13",
          "runs": 0
        },
        {
          "week": 12,
          "start": "2026-12-14",
          "end": "2026-12-20",
          "runs": 0
        },
        {
          "week": 13,
          "start": "2026-12-21",
          "end": "2026-12-27",
          "runs": 53
        }
      ]
    },
    "largest_survivable_shock": null,
    "curve": [
      {
        "shock": "0.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "1000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "1500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "2000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "2500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "3000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "3500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "4000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "4500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "5000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "5500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "6000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "6500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "7000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "7500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "8000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "8500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "9000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "9500.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "10000.00",
        "survival_pct": "0.00"
      }
    ],
    "extra_buffer": "48533.79",
    "bridge": {
      "day": "2026-11-05",
      "steps": [
        {
          "key": "cash",
          "label": "Cash today",
          "kind": "total",
          "amount": "156526.85",
          "start": "0",
          "end": "156526.85"
        },
        {
          "key": "bills",
          "label": "Bills and fixed payments to 5 Nov",
          "kind": "down",
          "amount": "-323699.25",
          "start": "156526.85",
          "end": "-167172.40"
        },
        {
          "key": "customers",
          "label": "Customers paying (average run)",
          "kind": "up",
          "amount": "157207.05",
          "start": "-167172.40",
          "end": "-9965.35"
        },
        {
          "key": "margin",
          "label": "Bad-luck margin",
          "kind": "margin",
          "amount": "-38568.44",
          "start": "-9965.35",
          "end": "-48533.79"
        },
        {
          "key": "worst",
          "label": "Worst likely position on 5 Nov",
          "kind": "total",
          "amount": "-48533.79",
          "start": "0",
          "end": "-48533.79"
        }
      ],
      "worst_likely": "-48533.79",
      "gap": "48533.79",
      "spare": "0.00"
    },
    "plan": {
      "actions": [
        "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>"
      ],
      "survival_pct": "0.00",
      "extra_buffer": "24645.36",
      "gap_on_shock_day": "0.00",
      "most_likely_failure_day": "2026-12-06"
    },
    "headline": {
      "case": "2",
      "line1": "Without action you'll be S$48,533.79 short on 5 Nov 2026 in a bad run.",
      "line2": "Best move: the best plan in the options comparison (3 action(s)); with it 96.10% of runs stay above zero."
    },
    "weekly": [
      {
        "week": 1,
        "start": "2026-09-28",
        "end": "2026-10-04",
        "lowest_p10": "74371.60",
        "lowest_p50": "74371.60",
        "lowest_p90": "86700.18"
      },
      {
        "week": 2,
        "start": "2026-10-05",
        "end": "2026-10-11",
        "lowest_p10": "69115.79",
        "lowest_p50": "77244.37",
        "lowest_p90": "114899.28"
      },
      {
        "week": 3,
        "start": "2026-10-12",
        "end": "2026-10-18",
        "lowest_p10": "67326.33",
        "lowest_p50": "113109.82",
        "lowest_p90": "113109.82"
      },
      {
        "week": 4,
        "start": "2026-10-19",
        "end": "2026-10-25",
        "lowest_p10": "95241.09",
        "lowest_p50": "108273.71",
        "lowest_p90": "157557.67"
      },
      {
        "week": 5,
        "start": "2026-10-26",
        "end": "2026-11-01",
        "lowest_p10": "70381.15",
        "lowest_p50": "107165.11",
        "lowest_p90": "129567.86"
      },
      {
        "week": 6,
        "start": "2026-11-02",
        "end": "2026-11-08",
        "lowest_p10": "-37291.21",
        "lowest_p50": "-9376.45",
        "lowest_p90": "30664.17"
      },
      {
        "week": 7,
        "start": "2026-11-09",
        "end": "2026-11-15",
        "lowest_p10": "-21376.45",
        "lowest_p50": "-9376.45",
        "lowest_p90": "29906.75"
      },
      {
        "week": 8,
        "start": "2026-11-16",
        "end": "2026-11-22",
        "lowest_p10": "-21376.45",
        "lowest_p50": "22952.60",
        "lowest_p90": "29906.75"
      },
      {
        "week": 9,
        "start": "2026-11-23",
        "end": "2026-11-29",
        "lowest_p10": "-5072.21",
        "lowest_p50": "26655.75",
        "lowest_p90": "65923.14"
      },
      {
        "week": 10,
        "start": "2026-11-30",
        "end": "2026-12-06",
        "lowest_p10": "-16933.79",
        "lowest_p50": "-5691.21",
        "lowest_p90": "26655.75"
      },
      {
        "week": 11,
        "start": "2026-12-07",
        "end": "2026-12-13",
        "lowest_p10": "-16933.79",
        "lowest_p50": "-9891.21",
        "lowest_p90": "29718.15"
      },
      {
        "week": 12,
        "start": "2026-12-14",
        "end": "2026-12-20",
        "lowest_p10": "-19809.25",
        "lowest_p50": "14964.00",
        "lowest_p90": "19800.11"
      },
      {
        "week": 13,
        "start": "2026-12-21",
        "end": "2026-12-27",
        "lowest_p10": "-13025.81",
        "lowest_p50": "-13025.81",
        "lowest_p90": "-13025.81"
      }
    ],
    "daily": [],
    "customers": [
      {
        "customer_id": "c-bayfront",
        "name": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
        "observed_payments": 24,
        "mean_delay_days": "22.5",
        "shortest_delay_days": 12,
        "longest_delay_days": 35,
        "forecast_delay_days": 22,
        "source": "measured"
      },
      {
        "customer_id": "c-kallang",
        "name": "<untrusted>Kallang Corner Stores</untrusted>",
        "observed_payments": 24,
        "mean_delay_days": "2.3",
        "shortest_delay_days": 0,
        "longest_delay_days": 6,
        "forecast_delay_days": 2,
        "source": "measured"
      },
      {
        "customer_id": "c-orchid",
        "name": "<untrusted>Orchid Bay Hospitality</untrusted>",
        "observed_payments": 12,
        "mean_delay_days": "23.6",
        "shortest_delay_days": 12,
        "longest_delay_days": 31,
        "forecast_delay_days": 24,
        "source": "measured"
      }
    ],
    "assumptions": [
      "2,000 simulated runs of the 13-week forecast to 2026-12-27, with a fixed seed (the same question always gives the same answer).",
      "Only the timing of customer payments is random: each invoice's delay is drawn from that customer's own past payments (an unpaid invoice only from delays longer than it is already late). Amounts, bills, payroll, rent, tax and scheduled payments are fixed.",
      "A saved payment-delay assumption moves that customer's delays so they centre on the saved number of days.",
      "A run fails if end-of-day cash goes below zero on any day. Survival = share of runs that never do. Target 95%.",
      "'Worst likely' and 'a bad run' = the 5th percentile of runs; P10 / P50 / P90 = the 10th, 50th and 90th percentile on each day.",
      "Not modelled: customers paying less than invoiced or stopping, more than one shock, and invoices first issued after the forecast's pattern. Plans with a credit line or loan are compared by compare_options; the headline uses its best plan."
    ]
  },
  "drivers": [
    {
      "label": "<untrusted>Bill MFI-88120 to Meridian Food Imports Pte. Ltd. due 2026-11-05</untrusted>",
      "amount": "-85000.00",
      "detail": "<untrusted>2026-11-05 (open_bill)</untrusted>"
    },
    {
      "label": "<untrusted>Bill BL-5048 to Meridian Food Imports Pte. Ltd. due 2026-10-03</untrusted>",
      "amount": "-61898.43",
      "detail": "<untrusted>2026-10-03 (open_bill)</untrusted>"
    },
    {
      "label": "<untrusted>Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-10-06</untrusted>",
      "amount": "-58512.92",
      "detail": "<untrusted>2026-11-05 (expected_bill)</untrusted>"
    },
    {
      "label": "<untrusted>payroll (monthly, around day 27)</untrusted>",
      "amount": "-39232.39",
      "detail": "<untrusted>2026-10-27 (recurring)</untrusted>"
    },
    {
      "label": "<untrusted>rent (monthly, around day 1)</untrusted>",
      "amount": "-12500.00",
      "detail": "<untrusted>2026-10-01 (recurring)</untrusted>"
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

`get_alerts`

```json
{
  "floor": "71877.30",
  "floor_source": "default",
  "alerts": {
    "value": [
      {
        "key": "<untrusted>threshold</untrusted>",
        "kind": "threshold",
        "severity": "critical",
        "title": "<untrusted>Cash below your floor of S$71,877.30</untrusted>",
        "message": "<untrusted>Cash is forecast to fall below your floor of S$71,877.30 from 2026-11-05 (week 6), reaching -S$13,025.81 on 2026-12-27 - the account would be overdrawn.</untrusted>",
        "impact": "84903.11",
        "event_date": "2026-11-05",
        "days_away": 36,
        "score": "16508.94",
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
        "message": "<untrusted>Not enough cash for Bill MFI-88120 to Meridian Food Imports Pte. Ltd. due 2026-11-05 (S$85,000.00). The forecast balance goes below zero on 2026-11-05 and bottoms out at -S$9,376.45 on 2026-11-05.</untrusted>",
        "impact": "9376.45",
        "event_date": "2026-11-05",
        "days_away": 36,
        "score": "1823.20",
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
        "key": "<untrusted>shortfall:payroll (monthly, around day 27)</untrusted>",
        "kind": "shortfall",
        "severity": "critical",
        "title": "<untrusted>Can't cover payroll (monthly, around day 27)</untrusted>",
        "message": "<untrusted>Not enough cash for payroll (monthly, around day 27) (S$39,232.39). The forecast balance goes below zero on 2026-12-27 and bottoms out at -S$13,025.81 on 2026-12-27.</untrusted>",
        "impact": "13025.81",
        "event_date": "2026-12-27",
        "days_away": 88,
        "score": "1036.14",
        "drivers": [
          {
            "label": "<untrusted>payroll (monthly, around day 27)</untrusted>",
            "amount": "-39232.39",
            "detail": "<untrusted>2026-12-27 (recurring)</untrusted>"
          }
        ]
      },
      {
        "key": "<untrusted>shortfall:Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-11-06</untrusted>",
        "kind": "shortfall",
        "severity": "critical",
        "title": "<untrusted>Can't cover Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-11-06</untrusted>",
        "message": "<untrusted>Not enough cash for Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-11-06 (S$58,512.92). The forecast balance goes below zero on 2026-12-06 and bottoms out at -S$9,891.21 on 2026-12-10.</untrusted>",
        "impact": "9891.21",
        "event_date": "2026-12-06",
        "days_away": 67,
        "score": "1033.41",
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

> **The chance is very high. In the stress test, 0.00% of the 2,000 simulated runs stay above zero through 27 Dec 2026.** The test draws each customer's payment delay from their past payment habits. It's a simulation, not a guarantee.
>
> **When it happens**
> - Cash today is S$156,526.85. Nothing goes wrong through October.
> - The first shortfall is on **5 Nov 2026**, and 83.70% of the runs fail on that day.
> - On that day, bills and fixed payments of S$323,699.25 meet expected customer receipts of S$157,207.05 in an average run. In a bad run (5th percentile) the account is S$48,533.79 short.
> - The main bills are Meridian Food Imports bill MFI-88120 for S$85,000.00 due 5 Nov, and an expected Meridian bill of S$58,512.92. The earlier Meridian bill BL-5048 (S$61,898.43) is due 3 Oct.
> - Cash dips again in early December, and payroll of S$39,232.39 on 27 Dec can't be covered. The forecast low is -S$13,025.81 on 27 Dec.
> - The alerts tool also shows cash falling below your floor of S$71,877.30 from 5 Nov. That floor is the default, not one you set.
>
> **What would help**
> - You would need about S$48,533.79 more cash to reach the 95% target.
> - Chasing Bayfront Grocers invoice INV-1062 (S$51,283.20) so it's paid by 19 Oct instead of 10 Nov helps. That alone isn't enough, though, and survival stays at 0.00% in that plan.
> - The best combined plan reaches 96.10% survival. I can run the options comparison to show what it includes, including financing and its cost.
>
> Bayfront is also 11 days overdue on INV-1057 (S$45,783.49). That is normal for them, since they usually pay about 22 days late. Should I run the options comparison?

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
| biz-straits | yes | 2 | `fa0c9113a7c1fdaa5a19325b575ba3458468ff271c5a386a79ab328a5765229f` |

Claude usage for this case: 2 calls, about US$0.038.
