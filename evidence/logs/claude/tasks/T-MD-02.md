# T-MD-02: Worst case, when cash runs out

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** In the worst case (sales -10 points, cost of sales +3 points, customers 15 days slower, costs +5% a year) month-end cash first goes below zero in April 2027. The owner needs the month, not only a general warning.

## Conversation

### Turn 1

**User:**

> What's the worst case for our cash over the next three years? When would we run out?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_financial_model` | {"case": "worst"} | **ok** | ok |

<details><summary>Tool result data</summary>

`get_financial_model`

```json
{
  "value": {
    "basis": "accrual",
    "starts_from": "2026-09-30",
    "first_month": "2026-10",
    "last_month": "2029-09",
    "drivers": [
      {
        "key": "sales_growth_pct",
        "label": "Sales growth",
        "unit": "% a year",
        "worst": "-10.23",
        "expected": "-0.23",
        "best": "9.77",
        "source": "measured: sales S$761,385.91 in the last 6 months vs S$762,258.52 in the 6 before, annualised"
      },
      {
        "key": "cost_of_sales_pct",
        "label": "Cost of sales",
        "unit": "% of sales",
        "worst": "53.63",
        "expected": "50.63",
        "best": "47.63",
        "source": "measured: cost of sales S$771,423.08 / sales S$1,523,644.43, last 12 months"
      },
      {
        "key": "cost_increase_pct",
        "label": "Cost increase (payroll and operating costs, from year 2)",
        "unit": "% a year",
        "worst": "5",
        "expected": "3",
        "best": "2",
        "source": "our assumption, not data"
      },
      {
        "key": "owner_drawings",
        "label": "Owner drawings",
        "unit": "S$ a month",
        "worst": "0.00",
        "expected": "0.00",
        "best": "0.00",
        "source": "none assumed"
      }
    ],
    "stock_cover_months": "0.74",
    "customers": [
      {
        "id": "c-bayfront",
        "name": "<untrusted>Bayfront Grocers Pte. Ltd.</untrusted>",
        "share": "0.6088",
        "terms_days": 30,
        "issue_days": [
          6,
          20
        ],
        "delay_worst": 37,
        "delay_expected": 22,
        "delay_best": 0,
        "delay_source": "measured average"
      },
      {
        "id": "c-orchid",
        "name": "<untrusted>Orchid Bay Hospitality</untrusted>",
        "share": "0.2374",
        "terms_days": 30,
        "issue_days": [
          5
        ],
        "delay_worst": 39,
        "delay_expected": 24,
        "delay_best": 0,
        "delay_source": "measured average"
      },
      {
        "id": "c-kallang",
        "name": "<untrusted>Kallang Corner Stores</untrusted>",
        "share": "0.1537",
        "terms_days": 14,
        "issue_days": [
          6,
          19
        ],
        "delay_worst": 17,
        "delay_expected": 2,
        "delay_best": 0,
        "delay_source": "measured average"
      }
    ],
    "suppliers": [
      {
        "id": "s-meridian",
        "name": "<untrusted>Meridian Food Imports Pte. Ltd.</untrusted>",
        "share": "0.7906",
        "terms_days": 30,
        "issue_days": [
          6
        ]
      },
      {
        "id": "s-harbour",
        "name": "<untrusted>Harbour Freight Lines</untrusted>",
        "share": "0.1247",
        "terms_days": 14,
        "issue_days": [
          6,
          20
        ]
      },
      {
        "id": "s-eastwind",
        "name": "<untrusted>Eastwind Packaging Supplies</untrusted>",
        "share": "0.0848",
        "terms_days": 30,
        "issue_days": [
          6
        ]
      }
    ],
    "loans": [
      {
        "id": "TL-20817",
        "lender": "<untrusted>Example Bank (fictional)</untrusted>",
        "balance_at_start": "79406.52",
        "last_payment_month": "2028-05"
      }
    ],
    "events": [],
    "actual_last_12_months": {
      "revenue": "1523644.43",
      "purchases": "845182.62",
      "cost_of_sales": "771423.08",
      "gross_profit": "752221.35",
      "operating_expenses": {
        "payroll": "562839.88",
        "rent": "150000.00",
        "utilities": "25086.46",
        "software": "7680.00",
        "other": "2867.75",
        "depreciation": "19500.00"
      },
      "total_operating_expenses": "767974.09",
      "operating_profit": "-15752.74",
      "other_income": "0.00",
      "interest": "6714.75",
      "net_profit": "-22467.49"
    },
    "cases": {
      "worst": {
        "case": "worst",
        "name": "Worst",
        "sales_growth_pct": "-10.23",
        "cost_of_sales_pct": "53.63",
        "cost_increase_pct": "5",
        "outlook": {
          "lowest_cash": "-600573.79",
          "lowest_cash_month": "2029-09",
          "first_month_below_zero": "2027-04",
          "cash_end_of_year": [
            "-72226.68",
            "-303363.98",
            "-600573.79"
          ],
          "revenue_by_year": [
            "1367775.60",
            "1227852.12",
            "1102242.84"
          ],
          "net_profit_by_year": [
            "-138074.43",
            "-234473.54",
            "-331290.32"
          ],
          "year1_revenue_vs_last_12_months": "-0.1023"
        },
        "years": [
          {
            "year": 1,
            "months": "Oct 2026 - Sep 2027",
            "pnl": {
              "revenue": "1367775.60",
              "purchases": "660929.34",
              "cost_of_sales": "733538.04",
              "gross_profit": "634237.56",
              "operating_expenses": {
                "payroll": "564388.68",
                "rent": "150000.00",
                "utilities": "25086.48",
                "software": "7680.00",
                "other": "2867.76",
                "depreciation": "18500.00"
              },
              "total_operating_expenses": "768522.92",
              "operating_profit": "-134285.36",
              "other_income": "0.00",
              "interest": "3789.07",
              "net_profit": "-138074.43"
            },
            "cash_flow": {
              "net_profit": "-138074.43",
              "add_depreciation": "18500.00",
              "working_capital": {
                "receivables": "-42784.63",
                "inventory": "72608.70",
                "payables": "-96794.83",
                "gst_payable": "4402.59",
                "cpf_payable": "0.00"
              },
              "operating": "-182142.60",
              "investing": "0.00",
              "financing_loan_principal": "-46610.93",
              "new_borrowing": "0.00",
              "owner_drawings": "0.00",
              "financing": "-46610.93",
              "net_change": "-228753.53",
              "opening_cash": "156526.85",
              "closing_cash": "-72226.68"
            },
            "balance_sheet": {
              "as_of": "2027-09-30",
              "cash": "-72226.68",
              "receivables": "229378.62",
              "inventory": "45234.85",
              "unmatched_supplier_payments": "0.00",
              "fixed_assets_cost": "155000.00",
              "accumulated_depreciation": "102500.00",
              "fixed_assets_net": "52500.00",
              "total_assets": "254886.79",
              "payables": "62476.23",
              "gst_payable": "14270.34",
              "cpf_payable": "7800.00",
              "unmatched_customer_receipts": "0.00",
              "accrued_costs": "0.00",
              "loans": "32795.59",
              "loans_due_within_12_months": "32795.59",
              "loans_due_after_12_months": "0.00",
              "other_borrowings": "0.00",
              "total_liabilities": "117342.16",
              "share_capital": "150000.00",
              "retained_earnings": "-12455.37",
              "owner_drawings": "0.00",
              "total_equity": "137544.63"
            },
            "ratios": {
              "gross_margin": "0.4637",
              "operating_margin": "-0.0982",
              "net_margin": "-0.1009",
              "ebitda": "-115785.36",
              "current_ratio": "1.72",
              "debt_ratio": "0.4604"
            }
          },
          {
            "year": 2,
            "months": "Oct 2027 - Sep 2028",
            "pnl": {
              "revenue": "1227852.12",
              "purchases": "653869.59",
              "cost_of_sales": "658497.12",
              "gross_profit": "569355.00",
              "operating_expenses": {
                "payroll": "592608.12",
                "rent": "157500.00",
                "utilities": "26340.84",
                "software": "8064.00",
                "other": "3011.16",
                "depreciation": "15500.00"
              },
              "total_operating_expenses": "803024.12",
              "operating_profit": "-233669.12",
              "other_income": "0.00",
              "interest": "804.42",
              "net_profit": "-234473.54"
            },
            "cash_flow": {
              "net_profit": "-234473.54",
              "add_depreciation": "15500.00",
              "working_capital": {
                "receivables": "23465.42",
                "inventory": "4627.53",
                "payables": "-6391.32",
                "gst_payable": "-1459.80",
                "cpf_payable": "390.00"
              },
              "operating": "-198341.71",
              "investing": "0.00",
              "financing_loan_principal": "-32795.59",
              "new_borrowing": "0.00",
              "owner_drawings": "0.00",
              "financing": "-32795.59",
              "net_change": "-231137.30",
              "opening_cash": "-72226.68",
              "closing_cash": "-303363.98"
            },
            "balance_sheet": {
              "as_of": "2028-09-30",
              "cash": "-303363.98",
              "receivables": "205913.20",
              "inventory": "40607.32",
              "unmatched_supplier_payments": "0.00",
              "fixed_assets_cost": "155000.00",
              "accumulated_depreciation": "118000.00",
              "fixed_assets_net": "37000.00",
              "total_assets": "-19843.46",
              "payables": "56084.91",
              "gst_payable": "12810.54",
              "cpf_payable": "8190.00",
              "unmatched_customer_receipts": "0.00",
              "accrued_costs": "0.00",
              "loans": "0.00",
              "loans_due_within_12_months": "0.00",
              "loans_due_after_12_months": "0.00",
              "other_borrowings": "0.00",
              "total_liabilities": "77085.45",
              "share_capital": "150000.00",
              "retained_earnings": "-246928.91",
              "owner_drawings": "0.00",
              "total_equity": "-96928.91"
            },
            "ratios": {
              "gross_margin": "0.4637",
              "operating_margin": "-0.1903",
              "net_margin": "-0.1910",
              "ebitda": "-218169.12",
              "current_ratio": "-0.74",
              "debt_ratio": "-3.8847"
            }
          },
          {
            "year": 3,
            "months": "Oct 2028 - Sep 2029",
            "pnl": {
              "revenue": "1102242.84",
              "purchases": "586978.71",
              "cost_of_sales": "591132.84",
              "gross_profit": "511110.00",
              "operating_expenses": {
                "payroll": "622238.52",
                "rent": "165375.00",
                "utilities": "27657.84",
                "software": "8467.20",
                "other": "3161.76",
                "depreciation": "15500.00"
              },
              "total_operating_expenses": "842400.32",
              "operating_profit": "-331290.32",
              "other_income": "0.00",
              "interest": "0.00",
              "net_profit": "-331290.32"
            },
            "cash_flow": {
              "net_profit": "-331290.32",
              "add_depreciation": "15500.00",
              "working_capital": {
                "receivables": "21064.94",
                "inventory": "4154.13",
                "payables": "-5737.48",
                "gst_payable": "-1310.58",
                "cpf_payable": "409.50"
              },
              "operating": "-297209.81",
              "investing": "0.00",
              "financing_loan_principal": "0.00",
              "new_borrowing": "0.00",
              "owner_drawings": "0.00",
              "financing": "0.00",
              "net_change": "-297209.81",
              "opening_cash": "-303363.98",
              "closing_cash": "-600573.79"
            },
            "balance_sheet": {
              "as_of": "2029-09-30",
              "cash": "-600573.79",
              "receivables": "184848.26",
              "inventory": "36453.19",
              "unmatched_supplier_payments": "0.00",
              "fixed_assets_cost": "155000.00",
              "accumulated_depreciation": "133500.00",
              "fixed_assets_net": "21500.00",
              "total_assets": "-357772.34",
              "payables": "50347.43",
              "gst_payable": "11499.96",
              "cpf_payable": "8599.50",
              "unmatched_customer_receipts": "0.00",
              "accrued_costs": "0.00",
              "loans": "0.00",
              "loans_due_within_12_months": "0.00",
              "loans_due_after_12_months": "0.00",
              "other_borrowings": "0.00",
              "total_liabilities": "70446.89",
              "share_capital": "150000.00",
              "retained_earnings": "-578219.23",
              "owner_drawings": "0.00",
              "total_equity": "-428219.23"
            },
            "ratios": {
              "gross_margin": "0.4637",
              "operating_margin": "-0.3006",
              "net_margin": "-0.3006",
              "ebitda": "-315790.32",
              "current_ratio": "-5.38",
              "debt_ratio": "-0.1969"
            }
          }
        ],
        "checks": {
          "balance_sheet_difference": "0.00",
          "indirect_minus_direct_cash": "0.00",
          "balanced": true,
          "cash_agrees": true
        },
        "monthly": []
      }
    },
    "notes": [
      "Accrual basis, amounts excluding GST; a projection from your books, not a promise.",
      "Month-end balances only: cash can dip inside a month. For the next 13 weeks day by day, use the 13-week forecast.",
      "Sales are flat within each year: year n = the last 12 months' average x (1 + growth)^n.",
      "Customers keep their share of sales and pay on their terms plus their delay; suppliers keep their share and are paid on their terms.",
      "Stock is kept at the usual cover of cost of sales; when there is more stock than that, purchases pause until it is used.",
      "Payroll is the latest payroll run; CPF is paid the month after. Other operating costs are the last 12 months' average per line. Both rise by the cost increase from year 2.",
      "Loan repayments follow the lender's schedule; GST owed at each quarter-end is paid the month after; depreciation follows each asset's life.",
      "Not modelled: income tax, new loans or asset purchases, seasonality, new customers."
    ]
  },
  "drivers": [
    {
      "label": "<untrusted>Worst case: lowest month-end cash</untrusted>",
      "amount": "-600573.79",
      "detail": "<untrusted>Sep 2029</untrusted>"
    },
    {
      "label": "<untrusted>Expected case: lowest month-end cash</untrusted>",
      "amount": "-642.25",
      "detail": "<untrusted>Jul 2029</untrusted>"
    },
    {
      "label": "<untrusted>Best case: lowest month-end cash</untrusted>",
      "amount": "199823.39",
      "detail": "<untrusted>Nov 2026</untrusted>"
    },
    {
      "label": "<untrusted>Expected case: month-end cash first below zero</untrusted>",
      "amount": null,
      "detail": "<untrusted>Jul 2029</untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2025-10-01",
    "period_end": "2026-09-30",
    "record_count": 12
  },
  "warnings": [
    "Income tax is not modelled, so profit is before tax."
  ]
}
```

</details>

**Assistant:**

> **In the worst case, month-end cash first goes below zero in April 2027, about 7 months from now.** This is the 3-year model's worst case on an accrual basis. It is a projection, not a promise.
>
> **Cash at the end of each year (worst case):**
> - Year 1 (Sep 2027): S$-72,226.68. You start at S$156,526.85.
> - Year 2 (Sep 2028): S$-303,363.98
> - Year 3 (Sep 2029): S$-600,573.79, which is the lowest point.
>
> **What drives it:**
> - **Sales:** Sales fall 10.23% a year. Year-1 revenue is S$1,367,775.60, against S$1,523,644.43 over the last 12 months. This rate is measured from your last 12 months of sales.
> - **Cost of sales:** It rises to 53.63% of sales, from 50.63% in the expected case. This is also measured from your books.
> - **Operating costs:** They rise 5% a year from year 2. That figure is our assumption, not data.
> - **Losses:** Net profit is S$-138,074.43 in year 1, S$-234,473.54 in year 2 and S$-331,290.32 in year 3. Payroll (S$564,388.68 in year 1) and rent are fixed costs that don't shrink as sales fall.
> - **Customer payments:** Bayfront, your largest customer, is assumed to pay 37 days late. Orchid Bay is assumed to pay 39 days late.
>
> **Context:**
> - Over the last 12 months you already made a small operating loss of S$-15,752.74. The business is roughly break-even today, so the margin for error is thin.
> - In the expected case, cash only just dips below zero, to S$-642.25 in July 2029.
> - The model doesn't include income tax, new loans, new customers or seasonality.
> - It shows month-end balances only. For dips inside the next 13 weeks, I can run the 13-week forecast.
>
> I can also test what would change this, such as cutting costs, lifting prices or sales, or chasing late payers.

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
| biz-straits | yes | 1 | `f80cd287fb0a7f2a2fc5e9074d3c1423877c110b4adb1f26fb915c42f42041cd` |

Claude usage for this case: 2 calls, about US$0.032.
