# T-MD-04: What the projection is based on

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Every driver says where it comes from. Two are measured from the books (sales growth from the last 6 vs previous 6 months, cost of sales 50.63% from the last 12 months), and the 3% yearly cost increase is our assumption, not data. The answer must say so instead of presenting all inputs as facts.

## Conversation

### Turn 1

**User:**

> What is your 3-year projection based on? Which numbers are measured and which are assumptions?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_financial_model` | {"case": "expected"} | **ok** | ok |

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
      "expected": {
        "case": "expected",
        "name": "Expected",
        "sales_growth_pct": "-0.23",
        "cost_of_sales_pct": "50.63",
        "cost_increase_pct": "3",
        "outlook": {
          "lowest_cash": "-642.25",
          "lowest_cash_month": "2029-07",
          "first_month_below_zero": "2029-07",
          "cash_end_of_year": [
            "107372.23",
            "50559.02",
            "2454.35"
          ],
          "revenue_by_year": [
            "1520140.08",
            "1516643.76",
            "1513155.48"
          ],
          "net_profit_by_year": [
            "-21818.79",
            "-40061.06",
            "-64154.36"
          ],
          "year1_revenue_vs_last_12_months": "-0.0023"
        },
        "years": [
          {
            "year": 1,
            "months": "Oct 2026 - Sep 2027",
            "pnl": {
              "revenue": "1520140.08",
              "purchases": "699264.89",
              "cost_of_sales": "769646.88",
              "gross_profit": "750493.20",
              "operating_expenses": {
                "payroll": "564388.68",
                "rent": "150000.00",
                "utilities": "25086.48",
                "software": "7680.00",
                "other": "2867.76",
                "depreciation": "18500.00"
              },
              "total_operating_expenses": "768522.92",
              "operating_profit": "-18029.72",
              "other_income": "0.00",
              "interest": "3789.07",
              "net_profit": "-21818.79"
            },
            "cash_flow": {
              "net_profit": "-21818.79",
              "add_depreciation": "18500.00",
              "working_capital": {
                "receivables": "17094.22",
                "inventory": "70381.99",
                "payables": "-93719.40",
                "gst_payable": "7018.29",
                "cpf_payable": "0.00"
              },
              "operating": "-2543.69",
              "investing": "0.00",
              "financing_loan_principal": "-46610.93",
              "new_borrowing": "0.00",
              "owner_drawings": "0.00",
              "financing": "-46610.93",
              "net_change": "-49154.62",
              "opening_cash": "156526.85",
              "closing_cash": "107372.23"
            },
            "balance_sheet": {
              "as_of": "2027-09-30",
              "cash": "107372.23",
              "receivables": "169499.77",
              "inventory": "47461.56",
              "unmatched_supplier_payments": "0.00",
              "fixed_assets_cost": "155000.00",
              "accumulated_depreciation": "102500.00",
              "fixed_assets_net": "52500.00",
              "total_assets": "376833.56",
              "payables": "65551.66",
              "gst_payable": "16886.04",
              "cpf_payable": "7800.00",
              "unmatched_customer_receipts": "0.00",
              "accrued_costs": "0.00",
              "loans": "32795.59",
              "loans_due_within_12_months": "32795.59",
              "loans_due_after_12_months": "0.00",
              "other_borrowings": "0.00",
              "total_liabilities": "123033.29",
              "share_capital": "150000.00",
              "retained_earnings": "103800.27",
              "owner_drawings": "0.00",
              "total_equity": "253800.27"
            },
            "ratios": {
              "gross_margin": "0.4937",
              "operating_margin": "-0.0119",
              "net_margin": "-0.0144",
              "ebitda": "470.28",
              "current_ratio": "2.64",
              "debt_ratio": "0.3265"
            }
          },
          {
            "year": 2,
            "months": "Oct 2027 - Sep 2028",
            "pnl": {
              "revenue": "1516643.76",
              "purchases": "767767.60",
              "cost_of_sales": "767876.76",
              "gross_profit": "748767.00",
              "operating_expenses": {
                "payroll": "581320.32",
                "rent": "154500.00",
                "utilities": "25839.12",
                "software": "7910.40",
                "other": "2953.80",
                "depreciation": "15500.00"
              },
              "total_operating_expenses": "788023.64",
              "operating_profit": "-39256.64",
              "other_income": "0.00",
              "interest": "804.42",
              "net_profit": "-40061.06"
            },
            "cash_flow": {
              "net_profit": "-40061.06",
              "add_depreciation": "15500.00",
              "working_capital": {
                "receivables": "389.84",
                "inventory": "109.16",
                "payables": "-150.77",
                "gst_payable": "-38.79",
                "cpf_payable": "234.00"
              },
              "operating": "-24017.62",
              "investing": "0.00",
              "financing_loan_principal": "-32795.59",
              "new_borrowing": "0.00",
              "owner_drawings": "0.00",
              "financing": "-32795.59",
              "net_change": "-56813.21",
              "opening_cash": "107372.23",
              "closing_cash": "50559.02"
            },
            "balance_sheet": {
              "as_of": "2028-09-30",
              "cash": "50559.02",
              "receivables": "169109.93",
              "inventory": "47352.40",
              "unmatched_supplier_payments": "0.00",
              "fixed_assets_cost": "155000.00",
              "accumulated_depreciation": "118000.00",
              "fixed_assets_net": "37000.00",
              "total_assets": "304021.35",
              "payables": "65400.89",
              "gst_payable": "16847.25",
              "cpf_payable": "8034.00",
              "unmatched_customer_receipts": "0.00",
              "accrued_costs": "0.00",
              "loans": "0.00",
              "loans_due_within_12_months": "0.00",
              "loans_due_after_12_months": "0.00",
              "other_borrowings": "0.00",
              "total_liabilities": "90282.14",
              "share_capital": "150000.00",
              "retained_earnings": "63739.21",
              "owner_drawings": "0.00",
              "total_equity": "213739.21"
            },
            "ratios": {
              "gross_margin": "0.4937",
              "operating_margin": "-0.0259",
              "net_margin": "-0.0264",
              "ebitda": "-23756.64",
              "current_ratio": "2.96",
              "debt_ratio": "0.2970"
            }
          },
          {
            "year": 3,
            "months": "Oct 2028 - Sep 2029",
            "pnl": {
              "revenue": "1513155.48",
              "purchases": "766001.69",
              "cost_of_sales": "766110.60",
              "gross_profit": "747044.88",
              "operating_expenses": {
                "payroll": "598759.92",
                "rent": "159135.00",
                "utilities": "26614.20",
                "software": "8147.76",
                "other": "3042.36",
                "depreciation": "15500.00"
              },
              "total_operating_expenses": "811199.24",
              "operating_profit": "-64154.36",
              "other_income": "0.00",
              "interest": "0.00",
              "net_profit": "-64154.36"
            },
            "cash_flow": {
              "net_profit": "-64154.36",
              "add_depreciation": "15500.00",
              "working_capital": {
                "receivables": "388.94",
                "inventory": "108.91",
                "payables": "-150.42",
                "gst_payable": "-38.76",
                "cpf_payable": "241.02"
              },
              "operating": "-48104.67",
              "investing": "0.00",
              "financing_loan_principal": "0.00",
              "new_borrowing": "0.00",
              "owner_drawings": "0.00",
              "financing": "0.00",
              "net_change": "-48104.67",
              "opening_cash": "50559.02",
              "closing_cash": "2454.35"
            },
            "balance_sheet": {
              "as_of": "2029-09-30",
              "cash": "2454.35",
              "receivables": "168720.99",
              "inventory": "47243.49",
              "unmatched_supplier_payments": "0.00",
              "fixed_assets_cost": "155000.00",
              "accumulated_depreciation": "133500.00",
              "fixed_assets_net": "21500.00",
              "total_assets": "239918.83",
              "payables": "65250.47",
              "gst_payable": "16808.49",
              "cpf_payable": "8275.02",
              "unmatched_customer_receipts": "0.00",
              "accrued_costs": "0.00",
              "loans": "0.00",
              "loans_due_within_12_months": "0.00",
              "loans_due_after_12_months": "0.00",
              "other_borrowings": "0.00",
              "total_liabilities": "90333.98",
              "share_capital": "150000.00",
              "retained_earnings": "-415.15",
              "owner_drawings": "0.00",
              "total_equity": "149584.85"
            },
            "ratios": {
              "gross_margin": "0.4937",
              "operating_margin": "-0.0424",
              "net_margin": "-0.0424",
              "ebitda": "-48654.36",
              "current_ratio": "2.42",
              "debt_ratio": "0.3765"
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

> The 3-year projection is built from your own books, with a few assumptions on top. It's accrual basis, excludes GST, and runs from Oct 2026 to Sep 2029. The cases I quote below are the Expected case unless I say otherwise.
>
> **Measured from your data**
> - **Sales growth:** Expected is -0.23% a year. Sales were S$761,385.91 in the last 6 months, against S$762,258.52 in the 6 months before. The worst case is -10.23% and the best is 9.77%. Those two are simply ±10 points around the measured figure.
> - **Cost of sales:** 50.63% of sales, from the last 12 months (S$771,423.08 on S$1,523,644.43 of sales). The worst case is 53.63% and the best is 47.63%.
> - **Customer payment delays:** Each customer's measured average days late.
>   - Bayfront Grocers: 22 days in the Expected case, 37 in the worst case.
>   - Orchid Bay Hospitality: 24 days in the Expected case, 39 in the worst case.
>   - Kallang Corner Stores: 2 days in the Expected case, 17 in the worst case.
>   - The best case assumes no delay for any of them.
> - **Customer and supplier mix:** Each customer's and supplier's share of sales and purchases, plus their payment terms, come from the books. So do the loan balance and repayment schedule (S$79,406.52, last payment May 2028) and the stock cover.
> - **Operating costs:** Payroll is the latest payroll run. Rent, utilities, software and other costs are the last 12-month averages.
>
> **Assumptions, not data**
> - **Cost increase:** Payroll and operating costs rise from year 2 by 3% a year in the Expected case, 5% in the worst case and 2% in the best case.
> - **Owner drawings:** None assumed (S$0).
> - **Not modelled:** Income tax, new loans or asset purchases, seasonality and new customers. Sales are flat within each year.
>
> **What it shows (Expected case)**
> - Net profit is -S$21,818.79 in year 1, -S$40,061.06 in year 2 and -S$64,154.36 in year 3. The losses grow because costs rise while sales stay flat.
> - Cash falls from S$156,526.85 today to S$2,454.35 at the end of year 3. Month-end cash first goes below zero in Jul 2029, at -S$642.25.
> - In the worst case, lowest month-end cash is -S$600,573.79 (Sep 2029). In the best case it is S$199,823.39 (Nov 2026).
>
> This is a projection from your books, not a promise. I can re-run it with your own growth, cost or hiring figures if you want to test them.

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
| biz-straits | yes | 1 | `00ba1d205a2be08448a98e8a148b6c2ce14815997e305c2b49ea0fee5d384b24` |

Claude usage for this case: 2 calls, about US$0.035.
