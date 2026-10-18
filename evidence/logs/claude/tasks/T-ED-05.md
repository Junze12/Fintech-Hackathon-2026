# T-ED-05: Save a customer payment delay as a forecast assumption

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Bayfront usually pays 22 days after the due date; they now say 43. Saved as an assumption (not a one-off what-if), the forecast low point becomes -S$70,660.41 on 14 Nov, the same as run_what_if "Bayfront pays 3 weeks late" (algorithms.md, What-if). The forecast then names the assumption and still gives the low point from the imported data alone.

## Conversation

### Turn 1

**User:**

> Bayfront has told us they will pay 43 days after the due date from now on. Save that as a forecast assumption.

*Assistant (before calling tools):*

> I need Bayfront's customer ID first, so I'll look at the invoices.

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `list_invoices` |  | **ok** | ok |
| `get_ageing` |  | **ok** | ok |
| `save_assumption` | {"kind": "payment_delay", "customer_id": "c-bayfront", "days": 43, "reason": "Bayfront told us they will pay 43 days after the due date from now on"} | **pending** | Not done yet. The exact details and a confirmation code have been shown to the user, who must reply with that code. Do not ask for, repeat or guess the code, and do not say the action has happened. |

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

`save_assumption`

```json
{
  "kind": "payment_delay",
  "customer_id": "c-bayfront",
  "days": 43,
  "category": null,
  "monthly_amount": null,
  "start": null,
  "reason": "Bayfront told us they will pay 43 days after the due date from now on"
}
```

</details>

**Assistant:**

> I've prepared the assumption, but it isn't saved yet. You need to confirm it with the code shown to you.
>
> - **Customer:** Bayfront Grocers Pte. Ltd.
> - **Assumption:** pays 43 days after the due date. This replaces the measured average of 22.5 days late.
> - **Effect:** once saved, it changes the forecast, alerts and recommendations for everyone until it is removed.
>
> Bayfront has three open invoices totalling S$146,350.65. INV-1057 (S$45,783.49) is already 11 days overdue. The saved delay would push all three payments later.
>
> Once you've confirmed, I can re-run the forecast to show the new cash low point.

**Confirmation prompt** (written by code, shown to the user):

> Save a forecast assumption: Bayfront Grocers Pte. Ltd. pays 43 days after the due date. It changes the forecast, alerts, recommendations and financing need for everyone until removed. The forecast low point goes from -S$13,025.81 (2026-12-27) to -S$70,660.41 (2026-11-14). Reply 'confirm ****' to proceed; anything else cancels.

### Turn 2

**User:**

> confirm ****

**System notice** (written by code, not the model):

> Assumption as-68bca20a42 saved. The forecast uses it from now on.

### Turn 3

**User:**

> Will we run out of cash?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `forecast_balance` |  | **ok** | ok |
| `list_adjustments` |  | **ok** | ok |

<details><summary>Tool result data</summary>

`forecast_balance`

```json
{
  "value": {
    "as_of": "2026-09-30",
    "start_balance": "156526.85",
    "weeks": [
      {
        "week": 1,
        "start": "2026-09-28",
        "end": "2026-10-04",
        "inflows": "0",
        "outflows": "82155.25",
        "end_balance": "74371.60",
        "min_balance": "74371.60"
      },
      {
        "week": 2,
        "start": "2026-10-05",
        "end": "2026-10-11",
        "inflows": "12328.58",
        "outflows": "9455.81",
        "end_balance": "77244.37",
        "min_balance": "77244.37"
      },
      {
        "week": 3,
        "start": "2026-10-12",
        "end": "2026-10-18",
        "inflows": "0",
        "outflows": "9918.04",
        "end_balance": "67326.33",
        "min_balance": "67326.33"
      },
      {
        "week": 4,
        "start": "2026-10-19",
        "end": "2026-10-25",
        "inflows": "11242.58",
        "outflows": "4836.11",
        "end_balance": "73732.80",
        "min_balance": "62490.22"
      },
      {
        "week": 5,
        "start": "2026-10-26",
        "end": "2026-11-01",
        "inflows": "73698.25",
        "outflows": "61635.14",
        "end_balance": "85795.91",
        "min_balance": "24597.66"
      },
      {
        "week": 6,
        "start": "2026-11-02",
        "end": "2026-11-08",
        "inflows": "11242.58",
        "outflows": "155698.90",
        "end_balance": "-58660.41",
        "min_balance": "-58660.41"
      },
      {
        "week": 7,
        "start": "2026-11-09",
        "end": "2026-11-15",
        "inflows": "0",
        "outflows": "12000.00",
        "end_balance": "-70660.41",
        "min_balance": "-70660.41"
      },
      {
        "week": 8,
        "start": "2026-11-16",
        "end": "2026-11-22",
        "inflows": "60526.54",
        "outflows": "6954.15",
        "end_balance": "-17088.02",
        "min_balance": "-28330.60"
      },
      {
        "week": 9,
        "start": "2026-11-23",
        "end": "2026-11-29",
        "inflows": "31727.96",
        "outflows": "39267.39",
        "end_balance": "-24627.45",
        "min_balance": "-56320.41"
      },
      {
        "week": 10,
        "start": "2026-11-30",
        "end": "2026-12-06",
        "inflows": "62525.78",
        "outflows": "83198.90",
        "end_balance": "-45300.57",
        "min_balance": "-45300.57"
      },
      {
        "week": 11,
        "start": "2026-12-07",
        "end": "2026-12-13",
        "inflows": "0",
        "outflows": "4200.00",
        "end_balance": "-49500.57",
        "min_balance": "-49500.57"
      },
      {
        "week": 12,
        "start": "2026-12-14",
        "end": "2026-12-20",
        "inflows": "39609.36",
        "outflows": "14754.15",
        "end_balance": "-24645.36",
        "min_balance": "-57300.57"
      },
      {
        "week": 13,
        "start": "2026-12-21",
        "end": "2026-12-27",
        "inflows": "11242.58",
        "outflows": "39232.39",
        "end_balance": "-52635.17",
        "min_balance": "-52635.17"
      }
    ],
    "low_point": {
      "date": "2026-11-14",
      "balance": "-70660.41",
      "week": 7
    },
    "items": [
      {
        "date": "2026-10-01",
        "amount": "-12500.00",
        "source": "recurring",
        "label": "<untrusted>rent (monthly, around day 1)</untrusted>",
        "ref": "rent",
        "counterparty_id": null
      },
      {
        "date": "2026-10-03",
        "amount": "-61898.43",
        "source": "open_bill",
        "label": "<untrusted>Bill BL-5048 to Meridian Food Imports Pte. Ltd. due 2026-10-03</untrusted>",
        "ref": "b-0048",
        "counterparty_id": "s-meridian"
      },
      {
        "date": "2026-10-03",
        "amount": "-640.00",
        "source": "recurring",
        "label": "<untrusted>software (monthly, around day 3)</untrusted>",
        "ref": "software",
        "counterparty_id": null
      },
      {
        "date": "2026-10-04",
        "amount": "-7116.82",
        "source": "open_bill",
        "label": "<untrusted>Bill BL-5049 to Eastwind Packaging Supplies due 2026-10-04</untrusted>",
        "ref": "b-0049",
        "counterparty_id": "s-eastwind"
      },
      {
        "date": "2026-10-05",
        "amount": "-5255.81",
        "source": "open_bill",
        "label": "<untrusted>Bill BL-5051 to Harbour Freight Lines due 2026-10-05</untrusted>",
        "ref": "b-0051",
        "counterparty_id": "s-harbour"
      },
      {
        "date": "2026-10-05",
        "amount": "12328.58",
        "source": "open_invoice",
        "label": "<untrusted>Invoice INV-1065 from Kallang Corner Stores (due 2026-10-03)</untrusted>",
        "ref": "i-0065",
        "counterparty_id": "c-kallang"
      },
      {
        "date": "2026-10-10",
        "amount": "-4200.00",
        "source": "recurring",
        "label": "<untrusted>loan repayment (monthly, around day 10)</untrusted>",
        "ref": "loan_repayment",
        "counterparty_id": null
      },
      {
        "date": "2026-10-14",
        "amount": "-7800.00",
        "source": "recurring",
        "label": "<untrusted>payroll (monthly, around day 14)</untrusted>",
        "ref": "payroll",
        "counterparty_id": null
      },
      {
        "date": "2026-10-18",
        "amount": "-2118.04",
        "source": "recurring",
        "label": "<untrusted>utilities (monthly, around day 18)</untrusted>",
        "ref": "utilities",
        "counterparty_id": null
      },
      {
        "date": "2026-10-20",
        "amount": "-4836.11",
        "source": "expected_bill",
        "label": "<untrusted>Expected bill to Harbour Freight Lines, issued around 2026-10-06</untrusted>",
        "ref": null,
        "counterparty_id": "s-harbour"
      },
      {
        "date": "2026-10-22",
        "amount": "11242.58",
        "source": "expected_invoice",
        "label": "<untrusted>Expected invoice from Kallang Corner Stores, issued around 2026-10-06</untrusted>",
        "ref": null,
        "counterparty_id": "c-kallang"
      },
      {
        "date": "2026-10-27",
        "amount": "-39232.39",
        "source": "recurring",
        "label": "<untrusted>payroll (monthly, around day 27)</untrusted>",
        "ref": "payroll",
        "counterparty_id": null
      },
      {
        "date": "2026-10-28",
        "amount": "-35.00",
        "source": "recurring",
        "label": "<untrusted>other (monthly, around day 28)</untrusted>",
        "ref": "other",
        "counterparty_id": null
      },
      {
        "date": "2026-10-29",
        "amount": "-9867.75",
        "source": "recurring",
        "label": "<untrusted>GST return 2026-07-01 to 2026-09-30 (output tax - input tax on invoices and bills)</untrusted>",
        "ref": "tax",
        "counterparty_id": null
      },
      {
        "date": "2026-10-31",
        "amount": "27914.76",
        "source": "open_invoice",
        "label": "<untrusted>Invoice INV-1063 from Orchid Bay Hospitality (due 2026-10-07)</untrusted>",
        "ref": "i-0063",
        "counterparty_id": "c-orchid"
      },
      {
        "date": "2026-11-01",
        "amount": "45783.49",
        "source": "open_invoice",
        "label": "<untrusted>Invoice INV-1057 from Bayfront Grocers Pte. Ltd. (due 2026-09-19)</untrusted>",
        "ref": "i-0057",
        "counterparty_id": "c-bayfront"
      },
      {
        "date": "2026-11-01",
        "amount": "-12500.00",
        "source": "recurring",
        "label": "<untrusted>rent (monthly, around day 1)</untrusted>",
        "ref": "rent",
        "counterparty_id": null
      },
      {
        "date": "2026-11-03",
        "amount": "-4836.11",
        "source": "expected_bill",
        "label": "<untrusted>Expected bill to Harbour Freight Lines, issued around 2026-10-20</untrusted>",
        "ref": null,
        "counterparty_id": "s-harbour"
      },
      {
        "date": "2026-11-03",
        "amount": "-640.00",
        "source": "recurring",
        "label": "<untrusted>software (monthly, around day 3)</untrusted>",
        "ref": "software",
        "counterparty_id": null
      },
      {
        "date": "2026-11-04",
        "amount": "11242.58",
        "source": "expected_invoice",
        "label": "<untrusted>Expected invoice from Kallang Corner Stores, issued around 2026-10-19</untrusted>",
        "ref": null,
        "counterparty_id": "c-kallang"
      },
      {
        "date": "2026-11-05",
        "amount": "-6709.87",
        "source": "expected_bill",
        "label": "<untrusted>Expected bill to Eastwind Packaging Supplies, issued around 2026-10-06</untrusted>",
        "ref": null,
        "counterparty_id": "s-eastwind"
      },
      {
        "date": "2026-11-05",
        "amount": "-58512.92",
        "source": "expected_bill",
        "label": "<untrusted>Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-10-06</untrusted>",
        "ref": null,
        "counterparty_id": "s-meridian"
      },
      {
        "date": "2026-11-05",
        "amount": "-85000.00",
        "source": "open_bill",
        "label": "<untrusted>Bill MFI-88120 to Meridian Food Imports Pte. Ltd. due 2026-11-05</untrusted>",
        "ref": "b-bulk-stock",
        "counterparty_id": "s-meridian"
      },
      {
        "date": "2026-11-10",
        "amount": "-4200.00",
        "source": "recurring",
        "label": "<untrusted>loan repayment (monthly, around day 10)</untrusted>",
        "ref": "loan_repayment",
        "counterparty_id": null
      },
      {
        "date": "2026-11-14",
        "amount": "-7800.00",
        "source": "recurring",
        "label": "<untrusted>payroll (monthly, around day 14)</untrusted>",
        "ref": "payroll",
        "counterparty_id": null
      },
      {
        "date": "2026-11-16",
        "amount": "49283.96",
        "source": "open_invoice",
        "label": "<untrusted>Invoice INV-1061 from Bayfront Grocers Pte. Ltd. (due 2026-10-04)</untrusted>",
        "ref": "i-0061",
        "counterparty_id": "c-bayfront"
      },
      {
        "date": "2026-11-18",
        "amount": "-2118.04",
        "source": "recurring",
        "label": "<untrusted>utilities (monthly, around day 18)</untrusted>",
        "ref": "utilities",
        "counterparty_id": null
      },
      {
        "date": "2026-11-20",
        "amount": "-4836.11",
        "source": "expected_bill",
        "label": "<untrusted>Expected bill to Harbour Freight Lines, issued around 2026-11-06</untrusted>",
        "ref": null,
        "counterparty_id": "s-harbour"
      },
      {
        "date": "2026-11-22",
        "amount": "11242.58",
        "source": "expected_invoice",
        "label": "<untrusted>Expected invoice from Kallang Corner Stores, issued around 2026-11-06</untrusted>",
        "ref": null,
        "counterparty_id": "c-kallang"
      },
      {
        "date": "2026-11-27",
        "amount": "-39232.39",
        "source": "recurring",
        "label": "<untrusted>payroll (monthly, around day 27)</untrusted>",
        "ref": "payroll",
        "counterparty_id": null
      },
      {
        "date": "2026-11-28",
        "amount": "31727.96",
        "source": "expected_invoice",
        "label": "<untrusted>Expected invoice from Orchid Bay Hospitality, issued around 2026-10-05</untrusted>",
        "ref": null,
        "counterparty_id": "c-orchid"
      },
      {
        "date": "2026-11-28",
        "amount": "-35.00",
        "source": "recurring",
        "label": "<untrusted>other (monthly, around day 28)</untrusted>",
        "ref": "other",
        "counterparty_id": null
      },
      {
        "date": "2026-12-01",
        "amount": "51283.20",
        "source": "open_invoice",
        "label": "<untrusted>Invoice INV-1062 from Bayfront Grocers Pte. Ltd. (due 2026-10-19)</untrusted>",
        "ref": "i-0062",
        "counterparty_id": "c-bayfront"
      },
      {
        "date": "2026-12-01",
        "amount": "-12500.00",
        "source": "recurring",
        "label": "<untrusted>rent (monthly, around day 1)</untrusted>",
        "ref": "rent",
        "counterparty_id": null
      },
      {
        "date": "2026-12-03",
        "amount": "-640.00",
        "source": "recurring",
        "label": "<untrusted>software (monthly, around day 3)</untrusted>",
        "ref": "software",
        "counterparty_id": null
      },
      {
        "date": "2026-12-04",
        "amount": "-4836.11",
        "source": "expected_bill",
        "label": "<untrusted>Expected bill to Harbour Freight Lines, issued around 2026-11-20</untrusted>",
        "ref": null,
        "counterparty_id": "s-harbour"
      },
      {
        "date": "2026-12-05",
        "amount": "11242.58",
        "source": "expected_invoice",
        "label": "<untrusted>Expected invoice from Kallang Corner Stores, issued around 2026-11-19</untrusted>",
        "ref": null,
        "counterparty_id": "c-kallang"
      },
      {
        "date": "2026-12-06",
        "amount": "-6709.87",
        "source": "expected_bill",
        "label": "<untrusted>Expected bill to Eastwind Packaging Supplies, issued around 2026-11-06</untrusted>",
        "ref": null,
        "counterparty_id": "s-eastwind"
      },
      {
        "date": "2026-12-06",
        "amount": "-58512.92",
        "source": "expected_bill",
        "label": "<untrusted>Expected bill to Meridian Food Imports Pte. Ltd., issued around 2026-11-06</untrusted>",
        "ref": null,
        "counterparty_id": "s-meridian"
      },
      {
        "date": "2026-12-10",
        "amount": "-4200.00",
        "source": "recurring",
        "label": "<untrusted>loan repayment (monthly, around day 10)</untrusted>",
        "ref": "loan_repayment",
        "counterparty_id": null
      },
      {
        "date": "2026-12-14",
        "amount": "-7800.00",
        "source": "recurring",
        "label": "<untrusted>payroll (monthly, around day 14)</untrusted>",
        "ref": "payroll",
        "counterparty_id": null
      },
      {
        "date": "2026-12-18",
        "amount": "39609.36",
        "source": "expected_invoice",
        "label": "<untrusted>Expected invoice from Bayfront Grocers Pte. Ltd., issued around 2026-10-06</untrusted>",
        "ref": null,
        "counterparty_id": "c-bayfront"
      },
      {
        "date": "2026-12-18",
        "amount": "-2118.04",
        "source": "recurring",
        "label": "<untrusted>utilities (monthly, around day 18)</untrusted>",
        "ref": "utilities",
        "counterparty_id": null
      },
      {
        "date": "2026-12-20",
        "amount": "-4836.11",
        "source": "expected_bill",
        "label": "<untrusted>Expected bill to Harbour Freight Lines, issued around 2026-12-06</untrusted>",
        "ref": null,
        "counterparty_id": "s-harbour"
      },
      {
        "date": "2026-12-22",
        "amount": "11242.58",
        "source": "expected_invoice",
        "label": "<untrusted>Expected invoice from Kallang Corner Stores, issued around 2026-12-06</untrusted>",
        "ref": null,
        "counterparty_id": "c-kallang"
      },
      {
        "date": "2026-12-27",
        "amount": "-39232.39",
        "source": "recurring",
        "label": "<untrusted>payroll (monthly, around day 27)</untrusted>",
        "ref": "payroll",
        "counterparty_id": null
      }
    ],
    "assumptions": [
      "1 saved assumption(s) from the owner replace the measured figures (listed in saved_assumptions).",
      "Starts from total cash across all accounts on 2026-09-30.",
      "Open bills are paid on their due date (already-overdue bills: the next day).",
      "Customer payments arrive on the due date plus that customer's average delay, measured from past invoices.",
      "Invoices already later than that are assumed to arrive within 7 days.",
      "Future invoices and bills follow each customer's and supplier's last 6 months (typical issue days, median amount); the business pays suppliers on time.",
      "Recurring costs: loan repayment (monthly, around day 10): -S$4,200.00; other (monthly, around day 28): -S$35.00; payroll (monthly, around day 14): -S$7,800.00; payroll (monthly, around day 27): -S$39,232.39; rent (monthly, around day 1): -S$12,500.00; software (monthly, around day 3): -S$640.00; tax (quarterly, around day 29): -S$16,055.60; utilities (monthly, around day 18): -S$2,118.04.",
      "A GST payment for a quarter that has already ended is that quarter's output tax minus input tax from your invoices and bills (input tax on costs without a supplier bill is not counted).",
      "Not included: uncategorised one-off spending and any new customers or costs that don't follow past patterns."
    ],
    "saved_assumptions": [
      "<untrusted>Bayfront Grocers Pte. Ltd. pays 43 days after the due date (measured 22) [saved assumption as-68bca20a42]</untrusted>"
    ],
    "low_point_without_saved": {
      "date": "2026-12-27",
      "balance": "-13025.81",
      "week": 13
    }
  },
  "drivers": [
    {
      "label": "<untrusted>payroll (monthly, around day 14)</untrusted>",
      "amount": "-7800.00",
      "detail": "<untrusted>2026-11-14 (recurring)</untrusted>"
    },
    {
      "label": "<untrusted>loan repayment (monthly, around day 10)</untrusted>",
      "amount": "-4200.00",
      "detail": "<untrusted>2026-11-10 (recurring)</untrusted>"
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

`list_adjustments`

```json
{
  "open_months": [
    "2026-07",
    "2026-08",
    "2026-09"
  ],
  "adjustments": [],
  "saved_assumptions": [
    {
      "id": "as-68bca20a42",
      "kind": "payment_delay",
      "status": "active",
      "customer": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
      "days": 43,
      "category": null,
      "monthly_amount": null,
      "start": null,
      "reason": "<untrusted>Bayfront told us they will pay 43 days after the due date from now on</untrusted>",
      "created_by": "demo-owner"
    }
  ],
  "uncategorised_payments": [
    {
      "transaction_id": "t00158",
      "date": "2026-07-02",
      "amount": "307.50",
      "category": "uncategorised",
      "description": "<untrusted>MISC DEBIT 66270</untrusted>"
    }
  ]
}
```

</details>

**Assistant:**

> **Yes, on the current forecast cash goes negative.** The assumption is saved (as-68bca20a42) and the forecast already uses it.
>
> - **Today:** cash is S$156,526.85.
> - **Low point:** –S$70,660.41 on 2026-11-14.
> - **Below zero from:** the week of 2 November (week 6). Forecast cash stays negative through the end of the 13 weeks (–S$52,635.17 in the week ending 27 December).
> - **Without the Bayfront assumption:** the low point was –S$13,025.81 on 2026-12-27. The 43-day delay makes the gap much deeper and brings it forward.
>
> **What causes it**
> - Meridian bill MFI-88120 for S$85,000.00 falls due on 2026-11-05. An expected Meridian bill of S$58,512.92 lands the same week, on top of rent and other costs.
> - Bayfront owes S$146,350.65 across three open invoices. With the 43-day delay, those payments are forecast for 2026-11-01 (S$45,783.49), 2026-11-16 (S$49,283.96) and 2026-12-01 (S$51,283.20). That is too late to cover the early-November bills.
>
> Next, I can run recommend_actions or compare_options to find the cheapest fix. The options include chasing Bayfront, asking Meridian to wait on the S$85,000 bill, or financing.

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 4.

| Seq | Sim date | User | Role | Tool | Kind | Parameters | Outcome | Reason |
|---|---|---|---|---|---|---|---|---|
| 3 | 2026-09-30 | demo-owner | owner | `save_assumption` | write | {"category": null, "customer_id": "c-bayfront", "days": 43, "kind": "payment_delay", "monthly_amount": null, "reason": "Bayfront told us they will pay 43 days after the due date from now on", "start": null} | **pending** | awaiting code (pa-fa1f79735269) |
| 4 | 2026-09-30 | demo-owner | owner | `save_assumption` | write | {"category": null, "customer_id": "c-bayfront", "days": 43, "kind": "payment_delay", "monthly_amount": null, "reason": "Bayfront told us they will pay 43 days after the due date from now on", "start": null} | **confirmed** | pa-fa1f79735269 |
| 5 | 2026-09-30 | demo-owner | owner | `save_assumption` | write | {"category": null, "customer_id": "c-bayfront", "days": 43, "kind": "payment_delay", "monthly_amount": null, "reason": "Bayfront told us they will pay 43 days after the due date from now on", "start": null} | **executed** | Assumption as-68bca20a42 saved. The forecast uses it from now on. |

## Sandbox bank operations

| Seq | Sim date | Action | Object | Amount (S$) | Outcome | Reason |
|---|---|---|---|---|---|---|
| 1 | 2026-09-30 | save_assumption | as-68bca20a42 |  | **executed** |  |

**Balances:**

| Account | Before | After | Change |
|---|---|---|---|
| Operating account ••••8886 | S$151,526.85 | S$151,526.85 | S$0.00 |
| Reserve account ••••1570 | S$5,000.00 | S$5,000.00 | S$0.00 |

## Audit hash chain

| Business | Verified | Entries | Head hash |
|---|---|---|---|
| biz-straits | yes | 7 | `1b935ad985c204eb0448f6b67d20880ec2b37b9c0d48fc9711352dceb069d7c6` |

Claude usage for this case: 5 calls, about US$0.063.
