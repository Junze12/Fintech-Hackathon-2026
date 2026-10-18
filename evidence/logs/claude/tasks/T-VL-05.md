# T-VL-05: What the valuation is based on

**Result: PASS**  ·  suite: tasks  ·  scenario: `concentrated_b2b`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** The discount rate (20%), growth after year 3 (2%) and EBITDA multiple (4x) are our assumptions, not data; tax is the flat 17% headline rate. The answer must name them as assumptions rather than present them as measured facts.

## Conversation

### Turn 1

**User:**

> What is your valuation based on? Which inputs are assumptions?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_break_even_and_value` | {"part": "valuation"} | **ok** | ok |

<details><summary>Tool result data</summary>

`get_break_even_and_value`

```json
{
  "value": {
    "starts_from": "2026-09-30",
    "first_month": "2026-10",
    "last_month": "2029-09",
    "break_even": null,
    "valuation": {
      "disclaimer": "An estimate from your books and the stated assumptions, not advice and not a price. A buyer or lender would do their own valuation.",
      "inputs": [
        {
          "key": "discount_rate_pct",
          "label": "Discount rate",
          "value": "20",
          "unit": "% a year",
          "source": "our assumption, not data: typical for a small private firm"
        },
        {
          "key": "terminal_growth_pct",
          "label": "Growth after year 3",
          "value": "2",
          "unit": "% a year",
          "source": "our assumption, not data"
        },
        {
          "key": "ebitda_multiple",
          "label": "EBITDA multiple",
          "value": "4",
          "unit": "x year-1 EBITDA",
          "source": "our assumption, not data: for a small private business, not a market quote or a price"
        },
        {
          "key": "owner_salary_monthly",
          "label": "Owner's market salary deducted",
          "value": "0.00",
          "unit": "S$ a month",
          "source": "none deducted"
        },
        {
          "key": "tax_rate_pct",
          "label": "Income tax on positive operating profit",
          "value": "17",
          "unit": "%",
          "source": "Singapore headline corporate rate; partial exemption and past losses not applied, so slightly conservative"
        },
        {
          "key": "net_debt",
          "label": "Net debt (loans + other borrowings - cash)",
          "value": "-194994.50",
          "unit": "S$",
          "source": "from the balance sheet at 2026-09-30"
        }
      ],
      "model_drivers": [
        {
          "key": "sales_growth_pct",
          "label": "Sales growth",
          "unit": "% a year",
          "worst": "-8.87",
          "expected": "1.13",
          "best": "11.13",
          "source": "measured: sales S$594,548.01 in the last 6 months vs S$591,223.33 in the 6 before, annualised"
        },
        {
          "key": "cost_of_sales_pct",
          "label": "Cost of sales",
          "unit": "% of sales",
          "worst": "21.05",
          "expected": "18.05",
          "best": "15.05",
          "source": "measured: cost of sales S$214,060.16 / sales S$1,185,771.34, last 12 months"
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
      "bridge": {
        "as_of": "2026-09-30",
        "cash": "194994.50",
        "loans": "0.00",
        "other_borrowings": "0.00",
        "net_debt": "-194994.50",
        "loan_list": []
      },
      "book_equity": "266873.23",
      "cases": {
        "worst": {
          "case": "worst",
          "name": "Worst",
          "years": [
            {
              "year": 1,
              "months": "Oct 2026 - Sep 2027",
              "revenue": "1080593.40",
              "ebitda": "-19602.00",
              "operating_profit": "-35852.00",
              "owner_salary": "0.00",
              "tax": "0.00",
              "operating_cash_flow": "-84947.03",
              "interest_added_back": "0.00",
              "free_cash_flow": "-84947.03",
              "discount_factor": "0.833333",
              "present_value": "-70789.19"
            },
            {
              "year": 2,
              "months": "Oct 2027 - Sep 2028",
              "revenue": "984744.84",
              "ebitda": "-138911.04",
              "operating_profit": "-138911.04",
              "owner_salary": "0.00",
              "tax": "0.00",
              "operating_cash_flow": "-126918.48",
              "interest_added_back": "0.00",
              "free_cash_flow": "-126918.48",
              "discount_factor": "0.694444",
              "present_value": "-88137.83"
            },
            {
              "year": 3,
              "months": "Oct 2028 - Sep 2029",
              "revenue": "897397.92",
              "ebitda": "-253689.72",
              "operating_profit": "-253689.72",
              "owner_salary": "0.00",
              "tax": "0.00",
              "operating_cash_flow": "-242697.82",
              "interest_added_back": "0.00",
              "free_cash_flow": "-242697.82",
              "discount_factor": "0.578704",
              "present_value": "-140450.13"
            }
          ],
          "dcf": {
            "present_value_years_1_3": "-299377.15",
            "terminal_value": null,
            "present_value_terminal": null,
            "terminal_share": null,
            "enterprise_value": null,
            "equity_value": null,
            "not_meaningful": "Free cash flow in year 3 is -S$242,697.82: the business uses cash at the end of the projection, so a going-concern value isn't meaningful on these figures."
          },
          "multiple": {
            "year1_ebitda": "-19602.00",
            "ebitda_margin": "-0.0181",
            "multiple": "4",
            "enterprise_value": null,
            "equity_value": null,
            "not_meaningful": "Year-1 EBITDA is -S$19,602.00: a multiple of a loss isn't meaningful."
          },
          "sensitivity": {
            "discount_rate_pct": [
              {
                "input": "15",
                "equity_value": null
              },
              {
                "input": "20",
                "equity_value": null
              },
              {
                "input": "25",
                "equity_value": null
              }
            ],
            "terminal_growth_pct": [
              {
                "input": "0",
                "equity_value": null
              },
              {
                "input": "2",
                "equity_value": null
              },
              {
                "input": "3",
                "equity_value": null
              }
            ],
            "ebitda_multiple": [
              {
                "input": "3",
                "equity_value": null
              },
              {
                "input": "4",
                "equity_value": null
              },
              {
                "input": "5",
                "equity_value": null
              }
            ]
          }
        },
        "expected": {
          "case": "expected",
          "name": "Expected",
          "years": [
            {
              "year": 1,
              "months": "Oct 2026 - Sep 2027",
              "revenue": "1199170.56",
              "ebitda": "109989.84",
              "operating_profit": "93739.84",
              "owner_salary": "0.00",
              "tax": "15935.77",
              "operating_cash_flow": "106899.69",
              "interest_added_back": "0.00",
              "free_cash_flow": "90963.92",
              "discount_factor": "0.833333",
              "present_value": "75803.27"
            },
            {
              "year": 2,
              "months": "Oct 2027 - Sep 2028",
              "revenue": "1212721.20",
              "ebitda": "94912.44",
              "operating_profit": "94912.44",
              "owner_salary": "0.00",
              "tax": "16135.11",
              "operating_cash_flow": "94419.12",
              "interest_added_back": "0.00",
              "free_cash_flow": "78284.01",
              "discount_factor": "0.694444",
              "present_value": "54363.90"
            },
            {
              "year": 3,
              "months": "Oct 2028 - Sep 2029",
              "revenue": "1226424.96",
              "ebitda": "79175.52",
              "operating_profit": "79175.52",
              "owner_salary": "0.00",
              "tax": "13459.84",
              "operating_cash_flow": "78681.67",
              "interest_added_back": "0.00",
              "free_cash_flow": "65221.83",
              "discount_factor": "0.578704",
              "present_value": "37744.11"
            }
          ],
          "dcf": {
            "present_value_years_1_3": "167911.28",
            "terminal_value": "369590.37",
            "present_value_terminal": "213883.32",
            "terminal_share": "0.5602",
            "enterprise_value": "381794.60",
            "equity_value": "576789.10",
            "not_meaningful": null
          },
          "multiple": {
            "year1_ebitda": "109989.84",
            "ebitda_margin": "0.0917",
            "multiple": "4",
            "enterprise_value": "439959.36",
            "equity_value": "634953.86",
            "not_meaningful": null
          },
          "sensitivity": {
            "discount_rate_pct": [
              {
                "input": "15",
                "equity_value": "712649.62"
              },
              {
                "input": "20",
                "equity_value": "576789.10"
              },
              {
                "input": "25",
                "equity_value": "499354.25"
              }
            ],
            "terminal_growth_pct": [
              {
                "input": "0",
                "equity_value": "551626.35"
              },
              {
                "input": "2",
                "equity_value": "576789.10"
              },
              {
                "input": "3",
                "equity_value": "591590.71"
              }
            ],
            "ebitda_multiple": [
              {
                "input": "3",
                "equity_value": "524964.02"
              },
              {
                "input": "4",
                "equity_value": "634953.86"
              },
              {
                "input": "5",
                "equity_value": "744943.70"
              }
            ]
          }
        },
        "best": {
          "case": "best",
          "name": "Best",
          "years": [
            {
              "year": 1,
              "months": "Oct 2026 - Sep 2027",
              "revenue": "1317747.72",
              "ebitda": "246696.24",
              "operating_profit": "230446.24",
              "owner_salary": "0.00",
              "tax": "39175.86",
              "operating_cash_flow": "248461.07",
              "interest_added_back": "0.00",
              "free_cash_flow": "209285.21",
              "discount_factor": "0.833333",
              "present_value": "174404.34"
            },
            {
              "year": 2,
              "months": "Oct 2027 - Sep 2028",
              "revenue": "1464413.04",
              "ebitda": "353833.80",
              "operating_profit": "353833.80",
              "owner_salary": "0.00",
              "tax": "60151.75",
              "operating_cash_flow": "347007.93",
              "interest_added_back": "0.00",
              "free_cash_flow": "286856.18",
              "discount_factor": "0.694444",
              "present_value": "199205.68"
            },
            {
              "year": 3,
              "months": "Oct 2028 - Sep 2029",
              "revenue": "1627402.20",
              "ebitda": "474489.36",
              "operating_profit": "474489.36",
              "owner_salary": "0.00",
              "tax": "80663.19",
              "operating_cash_flow": "466887.12",
              "interest_added_back": "0.00",
              "free_cash_flow": "386223.93",
              "discount_factor": "0.578704",
              "present_value": "223509.22"
            }
          ],
          "dcf": {
            "present_value_years_1_3": "597119.24",
            "terminal_value": "2188602.27",
            "present_value_terminal": "1266552.24",
            "terminal_share": "0.6796",
            "enterprise_value": "1863671.48",
            "equity_value": "2058665.98",
            "not_meaningful": null
          },
          "multiple": {
            "year1_ebitda": "246696.24",
            "ebitda_margin": "0.1872",
            "multiple": "4",
            "enterprise_value": "986784.96",
            "equity_value": "1181779.46",
            "not_meaningful": null
          },
          "sensitivity": {
            "discount_rate_pct": [
              {
                "input": "15",
                "equity_value": "2840353.64"
              },
              {
                "input": "20",
                "equity_value": "2058665.98"
              },
              {
                "input": "25",
                "equity_value": "1620720.70"
              }
            ],
            "terminal_growth_pct": [
              {
                "input": "0",
                "equity_value": "1909659.83"
              },
              {
                "input": "2",
                "equity_value": "2058665.98"
              },
              {
                "input": "3",
                "equity_value": "2146316.65"
              }
            ],
            "ebitda_multiple": [
              {
                "input": "3",
                "equity_value": "935083.22"
              },
              {
                "input": "4",
                "equity_value": "1181779.46"
              },
              {
                "input": "5",
                "equity_value": "1428475.70"
              }
            ]
          }
        }
      }
    }
  },
  "drivers": [
    {
      "label": "<untrusted>Expected case: break-even</untrusted>",
      "amount": null,
      "detail": "<untrusted>Sales are at or above break-even every month.</untrusted>"
    },
    {
      "label": "<untrusted>Expected case: DCF equity value</untrusted>",
      "amount": "576789.10",
      "detail": "<untrusted></untrusted>"
    },
    {
      "label": "<untrusted>Expected case: EBITDA multiple equity value</untrusted>",
      "amount": "634953.86",
      "detail": "<untrusted></untrusted>"
    },
    {
      "label": "<untrusted>Book value of equity (accounting, not a price)</untrusted>",
      "amount": "266873.23",
      "detail": "<untrusted></untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2025-10-01",
    "period_end": "2026-09-30",
    "record_count": 12
  },
  "warnings": [
    "An estimate from your books and the stated assumptions, not advice and not a price. A buyer or lender would do their own valuation.",
    "Best case: 68% of the DCF value comes after year 3, so it rests mostly on the business carrying on as projected.",
    "No owner salary deducted: we can't tell whether payroll includes the owner. If the owner works unpaid, a buyer would deduct a market salary (give one to see the effect).",
    "Tax is a flat 17% of positive operating profit (partial exemption and past losses not applied). Break-even and EBITDA are before tax."
  ]
}
```

</details>

**Assistant:**

> This is an estimate, not advice and not a price.
>
> **What it's based on**
> - A 3-year monthly projection (Oct 2026 – Sep 2029) built from your books.
> - Two methods: a DCF of free cash flow after tax plus a terminal value, and a 4× year-1 EBITDA cross-check.
> - Both methods add your cash of S$194,994.50 and subtract loans. You have no loans, so net debt is –S$194,994.50.
>
> **Assumptions (not data)**
> - Discount rate: 20% a year.
> - Growth after year 3: 2% a year.
> - EBITDA multiple: 4× year-1 EBITDA. It is not a market quote.
> - Cost increase from year 2: 3% expected, 5% worst, 2% best.
> - Tax: a flat 17% of positive operating profit. It ignores partial exemption and past losses, so it is slightly conservative.
> - No owner salary is deducted, and no owner drawings are assumed. If you work unpaid, a buyer would likely deduct a market salary, which would lower the value. Give me a salary figure and I'll rerun it.
>
> **Measured from your books**
> - Sales growth is 1.13% a year in the expected case (–8.87% worst, 11.13% best). It compares the last 6 months with the 6 before.
> - Cost of sales is 18.05% of sales in the expected case (21.05% worst, 15.05% best). It comes from the last 12 months.
> - Cash is as of the 2026-09-30 balance sheet.
>
> **Results by case**
>
> | Case | DCF equity value | EBITDA-multiple equity value |
> |---|---|---|
> | Expected | S$576,789.10 | S$634,953.86 |
> | Best | S$2,058,665.98 | S$1,181,779.46 |
> | Worst | Not meaningful | Not meaningful |
>
> - **Expected case:** 56.02% of the DCF enterprise value comes from the terminal value. Book equity is S$266,873.23, which is an accounting figure.
> - **Worst case:** Free cash flow is negative through year 3 (–S$242,697.82 in year 3), so a going-concern value isn't meaningful. Year-1 EBITDA is also negative, so the multiple doesn't apply.
> - **Best case:** 67.96% of the DCF value comes after year 3. It depends heavily on the business carrying on as projected.
> - **Sensitivity, expected DCF:**
>   - Discount rate 15%: S$712,649.62.
>   - Discount rate 25%: S$499,354.25.
>   - Terminal growth 0%: S$551,626.35.
>   - Terminal growth 3%: S$591,590.71.
>   - Multiple 3×: S$524,964.02.
>   - Multiple 5×: S$744,943.70.

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
| biz-clearpath | yes | 1 | `698703a260ba7368d806dda7955ff8c7e57cdf9bbd397cb7166773a6407c2f86` |

Claude usage for this case: 2 calls, about US$0.033.
