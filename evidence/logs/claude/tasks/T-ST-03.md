# T-ST-03: Largest surprise payment a healthy business can absorb

**Result: PASS**  ·  suite: tasks  ·  scenario: `concentrated_b2b`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Clearpath Systems never goes below zero in any run. The question is how big a one-off payment on 1 Nov it could take and still stay above zero in 95% of runs: S$154,335.71, read from the same 2,000 runs. The answer must give that amount from the tool.

## Conversation

### Turn 1

**User:**

> How big a surprise payment could we absorb on 1 November and still be safe?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `stress_test_cash` | {"shock_date": "2026-11-01"} | **ok** | ok |

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
      "date": "2026-11-01"
    },
    "shock_day_used": "2026-11-01",
    "survival_pct": "100.00",
    "survival_without_shock_pct": "100.00",
    "meets_target": true,
    "failures": {
      "runs_failing": 0,
      "most_likely_day": null,
      "most_likely_day_share_pct": "0.00",
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
          "runs": 0
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
          "runs": 0
        },
        {
          "week": 10,
          "start": "2026-11-30",
          "end": "2026-12-06",
          "runs": 0
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
          "runs": 0
        }
      ]
    },
    "largest_survivable_shock": "154335.71",
    "curve": [
      {
        "shock": "0.00",
        "survival_pct": "100.00"
      },
      {
        "shock": "20000.00",
        "survival_pct": "100.00"
      },
      {
        "shock": "40000.00",
        "survival_pct": "100.00"
      },
      {
        "shock": "60000.00",
        "survival_pct": "100.00"
      },
      {
        "shock": "80000.00",
        "survival_pct": "100.00"
      },
      {
        "shock": "100000.00",
        "survival_pct": "100.00"
      },
      {
        "shock": "120000.00",
        "survival_pct": "100.00"
      },
      {
        "shock": "140000.00",
        "survival_pct": "100.00"
      },
      {
        "shock": "160000.00",
        "survival_pct": "33.15"
      },
      {
        "shock": "180000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "200000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "220000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "240000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "260000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "280000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "300000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "320000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "340000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "360000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "380000.00",
        "survival_pct": "0.00"
      },
      {
        "shock": "400000.00",
        "survival_pct": "0.00"
      }
    ],
    "extra_buffer": "0.00",
    "bridge": {
      "day": "2026-11-01",
      "steps": [
        {
          "key": "cash",
          "label": "Cash today",
          "kind": "total",
          "amount": "194994.50",
          "start": "0",
          "end": "194994.50"
        },
        {
          "key": "bills",
          "label": "Bills and fixed payments to 1 Nov",
          "kind": "down",
          "amount": "-117680.45",
          "start": "194994.50",
          "end": "77314.05"
        },
        {
          "key": "customers",
          "label": "Customers paying (average run)",
          "kind": "up",
          "amount": "97966.46",
          "start": "77314.05",
          "end": "175280.51"
        },
        {
          "key": "margin",
          "label": "Bad-luck margin",
          "kind": "margin",
          "amount": "0.00",
          "start": "175280.51",
          "end": "175280.51"
        },
        {
          "key": "worst",
          "label": "Worst likely position on 1 Nov",
          "kind": "total",
          "amount": "175280.51",
          "start": "0",
          "end": "175280.51"
        }
      ],
      "worst_likely": "175280.51",
      "gap": "0.00",
      "spare": "175280.51"
    },
    "plan": null,
    "headline": {
      "case": "1",
      "line1": "Cash stays above zero to 27 Dec 2026 without doing anything.",
      "line2": "100.00% of simulated runs never go below zero."
    },
    "weekly": [
      {
        "week": 1,
        "start": "2026-09-28",
        "end": "2026-10-04",
        "lowest_p10": "175157.80",
        "lowest_p50": "175157.80",
        "lowest_p90": "175157.80"
      },
      {
        "week": 2,
        "start": "2026-10-05",
        "end": "2026-10-11",
        "lowest_p10": "170614.72",
        "lowest_p50": "170614.72",
        "lowest_p90": "185395.98"
      },
      {
        "week": 3,
        "start": "2026-10-12",
        "end": "2026-10-18",
        "lowest_p10": "173930.37",
        "lowest_p50": "183678.80",
        "lowest_p90": "200621.32"
      },
      {
        "week": 4,
        "start": "2026-10-19",
        "end": "2026-10-25",
        "lowest_p10": "173930.37",
        "lowest_p50": "228413.55",
        "lowest_p90": "245356.07"
      },
      {
        "week": 5,
        "start": "2026-10-26",
        "end": "2026-11-01",
        "lowest_p10": "175280.51",
        "lowest_p50": "175280.51",
        "lowest_p90": "175280.51"
      },
      {
        "week": 6,
        "start": "2026-11-02",
        "end": "2026-11-08",
        "lowest_p10": "156052.89",
        "lowest_p50": "156052.89",
        "lowest_p90": "172543.92"
      },
      {
        "week": 7,
        "start": "2026-11-09",
        "end": "2026-11-15",
        "lowest_p10": "156052.89",
        "lowest_p50": "161726.74",
        "lowest_p90": "188335.28"
      },
      {
        "week": 8,
        "start": "2026-11-16",
        "end": "2026-11-22",
        "lowest_p10": "161726.74",
        "lowest_p50": "224963.16",
        "lowest_p90": "240106.09"
      },
      {
        "week": 9,
        "start": "2026-11-23",
        "end": "2026-11-29",
        "lowest_p10": "199720.34",
        "lowest_p50": "199720.34",
        "lowest_p90": "199720.34"
      },
      {
        "week": 10,
        "start": "2026-11-30",
        "end": "2026-12-06",
        "lowest_p10": "172692.72",
        "lowest_p50": "172692.72",
        "lowest_p90": "189183.75"
      },
      {
        "week": 11,
        "start": "2026-12-07",
        "end": "2026-12-13",
        "lowest_p10": "172692.72",
        "lowest_p50": "172692.72",
        "lowest_p90": "189183.75"
      },
      {
        "week": 12,
        "start": "2026-12-14",
        "end": "2026-12-20",
        "lowest_p10": "177718.14",
        "lowest_p50": "193566.50",
        "lowest_p90": "240960.32"
      },
      {
        "week": 13,
        "start": "2026-12-21",
        "end": "2026-12-27",
        "lowest_p10": "193566.50",
        "lowest_p50": "216442.17",
        "lowest_p90": "216442.17"
      }
    ],
    "daily": [],
    "customers": [
      {
        "customer_id": "c-lumen",
        "name": "<untrusted>Lumen Home Retail</untrusted>",
        "observed_payments": 12,
        "mean_delay_days": "40.2",
        "shortest_delay_days": 33,
        "longest_delay_days": 46,
        "forecast_delay_days": 40,
        "source": "measured"
      },
      {
        "customer_id": "c-northshore",
        "name": "<untrusted>Northshore Medical Group</untrusted>",
        "observed_payments": 12,
        "mean_delay_days": "4.3",
        "shortest_delay_days": 0,
        "longest_delay_days": 11,
        "forecast_delay_days": 4,
        "source": "measured"
      },
      {
        "customer_id": "c-pinewood",
        "name": "<untrusted>Pinewood Learning Centre</untrusted>",
        "observed_payments": 12,
        "mean_delay_days": "2.9",
        "shortest_delay_days": 0,
        "longest_delay_days": 6,
        "forecast_delay_days": 3,
        "source": "measured"
      },
      {
        "customer_id": "c-tidewater",
        "name": "<untrusted>Tidewater Port Logistics Pte. Ltd.</untrusted>",
        "observed_payments": 12,
        "mean_delay_days": "12.8",
        "shortest_delay_days": 0,
        "longest_delay_days": 19,
        "forecast_delay_days": 13,
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
      "label": "<untrusted>payroll (monthly, around day 27)</untrusted>",
      "amount": "-52120.25",
      "detail": "<untrusted>2026-10-27 (recurring)</untrusted>"
    },
    {
      "label": "<untrusted>GST return 2026-07-01 to 2026-09-30 (output tax - input tax on invoices and bills)</untrusted>",
      "amount": "-21889.81",
      "detail": "<untrusted>2026-10-29 (recurring)</untrusted>"
    },
    {
      "label": "<untrusted>Bill BL-5025 to Northpoint Contract Engineers due 2026-10-03</untrusted>",
      "amount": "-10836.70",
      "detail": "<untrusted>2026-10-03 (open_bill)</untrusted>"
    },
    {
      "label": "<untrusted>payroll (monthly, around day 14)</untrusted>",
      "amount": "-9100.00",
      "detail": "<untrusted>2026-10-14 (recurring)</untrusted>"
    },
    {
      "label": "<untrusted>rent (monthly, around day 1)</untrusted>",
      "amount": "-7800.00",
      "detail": "<untrusted>2026-10-01 (recurring)</untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2025-10-01",
    "period_end": "2026-09-30",
    "record_count": 193
  },
  "warnings": []
}
```

</details>

**Assistant:**

> You could absorb a surprise payment of up to **S$154,335.71** on 1 November and still keep cash above zero in at least 95% of simulated runs.
>
> - **Survival:** In the simulations, 100% of runs stay above zero for any shock up to S$140,000. At S$160,000, only 33.15% of runs survive. At S$180,000, none do. The S$154,335.71 figure is the point where survival falls to the 95% target.
> - **How the cash gets there:**
>   - Cash today is S$194,994.50.
>   - Bills and fixed payments before 1 November take S$117,680.45. The main ones are payroll of S$52,120.25 on 27 October and the GST return of S$21,889.81 on 29 October.
>   - Customer payments add S$97,966.46 in an average run.
>   - That leaves a worst likely position of S$175,280.51 on 1 November.
> - **Without a shock:** Cash stays above zero to 27 December 2026 in 100% of runs.
>
> This is a simulation of customer payment timing based on past habits, not a guarantee. It does not model customers paying less than invoiced or stopping payment. It also doesn't model more than one shock. Lumen Home Retail is the slowest payer, at about 40 days late on average, so a delay there is the main risk.
>
> The test uses a floor of zero. If you want a cushion above zero, I can re-run it with a buffer.

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
| biz-clearpath | yes | 1 | `ebd31ec3df8e209a3b2f477fe3a609bf92e063aeb20b2b9a571fe95f42882146` |

Claude usage for this case: 2 calls, about US$0.029.
