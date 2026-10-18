# T-VL-04: A value that isn't meaningful

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** On Straits Harbour's expected case the business uses cash in year 3 (free cash flow -S$48,104.67) and year-1 EBITDA is S$470.28 (0.03% of sales), so neither the DCF nor the multiple gives a meaningful value. The answer must say so instead of inventing a figure, and can give the best case (DCF equity value S$1,152,458.86, 67% of it after year 3).

## Conversation

### Turn 1

**User:**

> What is the business worth in the expected case, and in the best case?

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
          "value": "-77120.33",
          "unit": "S$",
          "source": "from the balance sheet at 2026-09-30"
        }
      ],
      "model_drivers": [
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
      "bridge": {
        "as_of": "2026-09-30",
        "cash": "156526.85",
        "loans": "79406.52",
        "other_borrowings": "0.00",
        "net_debt": "-77120.33",
        "loan_list": [
          {
            "id": "TL-20817",
            "lender": "<untrusted>Example Bank (fictional)</untrusted>",
            "balance_at_start": "79406.52",
            "last_payment_month": "2028-05"
          }
        ]
      },
      "book_equity": "275619.06",
      "cases": {
        "worst": {
          "case": "worst",
          "name": "Worst",
          "years": [
            {
              "year": 1,
              "months": "Oct 2026 - Sep 2027",
              "revenue": "1367775.60",
              "ebitda": "-115785.36",
              "operating_profit": "-134285.36",
              "owner_salary": "0.00",
              "tax": "0.00",
              "operating_cash_flow": "-182142.60",
              "interest_added_back": "3789.07",
              "free_cash_flow": "-178353.53",
              "discount_factor": "0.833333",
              "present_value": "-148627.94"
            },
            {
              "year": 2,
              "months": "Oct 2027 - Sep 2028",
              "revenue": "1227852.12",
              "ebitda": "-218169.12",
              "operating_profit": "-233669.12",
              "owner_salary": "0.00",
              "tax": "0.00",
              "operating_cash_flow": "-198341.71",
              "interest_added_back": "804.42",
              "free_cash_flow": "-197537.29",
              "discount_factor": "0.694444",
              "present_value": "-137178.67"
            },
            {
              "year": 3,
              "months": "Oct 2028 - Sep 2029",
              "revenue": "1102242.84",
              "ebitda": "-315790.32",
              "operating_profit": "-331290.32",
              "owner_salary": "0.00",
              "tax": "0.00",
              "operating_cash_flow": "-297209.81",
              "interest_added_back": "0.00",
              "free_cash_flow": "-297209.81",
              "discount_factor": "0.578704",
              "present_value": "-171996.42"
            }
          ],
          "dcf": {
            "present_value_years_1_3": "-457803.03",
            "terminal_value": null,
            "present_value_terminal": null,
            "terminal_share": null,
            "enterprise_value": null,
            "equity_value": null,
            "not_meaningful": "Free cash flow in year 3 is -S$297,209.81: the business uses cash at the end of the projection, so a going-concern value isn't meaningful on these figures."
          },
          "multiple": {
            "year1_ebitda": "-115785.36",
            "ebitda_margin": "-0.0847",
            "multiple": "4",
            "enterprise_value": null,
            "equity_value": null,
            "not_meaningful": "Year-1 EBITDA is -S$115,785.36: a multiple of a loss isn't meaningful."
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
              "revenue": "1520140.08",
              "ebitda": "470.28",
              "operating_profit": "-18029.72",
              "owner_salary": "0.00",
              "tax": "0.00",
              "operating_cash_flow": "-2543.69",
              "interest_added_back": "3789.07",
              "free_cash_flow": "1245.38",
              "discount_factor": "0.833333",
              "present_value": "1037.82"
            },
            {
              "year": 2,
              "months": "Oct 2027 - Sep 2028",
              "revenue": "1516643.76",
              "ebitda": "-23756.64",
              "operating_profit": "-39256.64",
              "owner_salary": "0.00",
              "tax": "0.00",
              "operating_cash_flow": "-24017.62",
              "interest_added_back": "804.42",
              "free_cash_flow": "-23213.20",
              "discount_factor": "0.694444",
              "present_value": "-16120.28"
            },
            {
              "year": 3,
              "months": "Oct 2028 - Sep 2029",
              "revenue": "1513155.48",
              "ebitda": "-48654.36",
              "operating_profit": "-64154.36",
              "owner_salary": "0.00",
              "tax": "0.00",
              "operating_cash_flow": "-48104.67",
              "interest_added_back": "0.00",
              "free_cash_flow": "-48104.67",
              "discount_factor": "0.578704",
              "present_value": "-27838.35"
            }
          ],
          "dcf": {
            "present_value_years_1_3": "-42920.81",
            "terminal_value": null,
            "present_value_terminal": null,
            "terminal_share": null,
            "enterprise_value": null,
            "equity_value": null,
            "not_meaningful": "Free cash flow in year 3 is -S$48,104.67: the business uses cash at the end of the projection, so a going-concern value isn't meaningful on these figures."
          },
          "multiple": {
            "year1_ebitda": "470.28",
            "ebitda_margin": "0.0003",
            "multiple": "4",
            "enterprise_value": null,
            "equity_value": null,
            "not_meaningful": "Year-1 EBITDA is S$470.28, under 2% of sales: too thin for a multiple to mean anything."
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
        "best": {
          "case": "best",
          "name": "Best",
          "years": [
            {
              "year": 1,
              "months": "Oct 2026 - Sep 2027",
              "revenue": "1672504.44",
              "ebitda": "125867.64",
              "operating_profit": "107367.64",
              "owner_salary": "0.00",
              "tax": "18252.50",
              "operating_cash_flow": "155567.64",
              "interest_added_back": "3789.07",
              "free_cash_flow": "141104.21",
              "discount_factor": "0.833333",
              "present_value": "117586.84"
            },
            {
              "year": 2,
              "months": "Oct 2027 - Sep 2028",
              "revenue": "1835908.20",
              "ebitda": "196441.68",
              "operating_profit": "180941.68",
              "owner_salary": "0.00",
              "tax": "30760.09",
              "operating_cash_flow": "185846.49",
              "interest_added_back": "804.42",
              "free_cash_flow": "155890.82",
              "discount_factor": "0.694444",
              "present_value": "108257.51"
            },
            {
              "year": 3,
              "months": "Oct 2028 - Sep 2029",
              "revenue": "2015276.40",
              "ebitda": "275076.36",
              "operating_profit": "259576.36",
              "owner_salary": "0.00",
              "tax": "44127.98",
              "operating_cash_flow": "264316.87",
              "interest_added_back": "0.00",
              "free_cash_flow": "220188.89",
              "discount_factor": "0.578704",
              "present_value": "127424.13"
            }
          ],
          "dcf": {
            "present_value_years_1_3": "353268.48",
            "terminal_value": "1247737.04",
            "present_value_terminal": "722070.05",
            "terminal_share": "0.6715",
            "enterprise_value": "1075338.53",
            "equity_value": "1152458.86",
            "not_meaningful": null
          },
          "multiple": {
            "year1_ebitda": "125867.64",
            "ebitda_margin": "0.0753",
            "multiple": "4",
            "enterprise_value": "503470.56",
            "equity_value": "580590.89",
            "not_meaningful": null
          },
          "sensitivity": {
            "discount_rate_pct": [
              {
                "input": "15",
                "equity_value": "1598421.92"
              },
              {
                "input": "20",
                "equity_value": "1152458.86"
              },
              {
                "input": "25",
                "equity_value": "902473.34"
              }
            ],
            "terminal_growth_pct": [
              {
                "input": "0",
                "equity_value": "1067509.44"
              },
              {
                "input": "2",
                "equity_value": "1152458.86"
              },
              {
                "input": "3",
                "equity_value": "1202429.11"
              }
            ],
            "ebitda_multiple": [
              {
                "input": "3",
                "equity_value": "454723.25"
              },
              {
                "input": "4",
                "equity_value": "580590.89"
              },
              {
                "input": "5",
                "equity_value": "706458.53"
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
      "detail": "<untrusted>Sales stay below break-even for all 3 years.</untrusted>"
    },
    {
      "label": "<untrusted>Expected case: DCF equity value</untrusted>",
      "amount": null,
      "detail": "<untrusted>not meaningful</untrusted>"
    },
    {
      "label": "<untrusted>Expected case: EBITDA multiple equity value</untrusted>",
      "amount": null,
      "detail": "<untrusted>not meaningful</untrusted>"
    },
    {
      "label": "<untrusted>Book value of equity (accounting, not a price)</untrusted>",
      "amount": "275619.06",
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
    "Best case: 67% of the DCF value comes after year 3, so it rests mostly on the business carrying on as projected.",
    "No owner salary deducted: we can't tell whether payroll includes the owner. If the owner works unpaid, a buyer would deduct a market salary (give one to see the effect).",
    "Tax is a flat 17% of positive operating profit (partial exemption and past losses not applied). Break-even and EBITDA are before tax."
  ]
}
```

</details>

**Assistant:**

> **Expected case: no meaningful value.** The model projects the business using cash in years 2 and 3. Free cash flow is S$1,245.38 in year 1, then -S$23,213.20 and -S$48,104.67. It never reaches break-even in the 3 years. Year-1 EBITDA is only S$470.28, which is too thin for a multiple. A DCF (discounted cash flow) or multiple value would be misleading here. For reference, book equity (an accounting figure, not a price) is S$275,619.06.
>
> **Best case (estimates, not advice and not a price):**
> - **DCF equity value:** S$1,152,458.86. This is enterprise value of S$1,075,338.53 plus net cash of S$77,120.33. About 67% of it comes from the terminal value after year 3, so it depends heavily on growth continuing.
> - **EBITDA-multiple cross-check:** S$580,590.89, using 4x year-1 EBITDA of S$125,867.64.
> - **DCF sensitivity to discount rate:** S$1,598,421.92 at 15%, and S$902,473.34 at 25%.
>
> **What drives the cases:**
> - **Sales growth:** -0.23% a year in expected and 9.77% in best. Both are measured from your last 12 months.
> - **Cost of sales:** 50.63% of sales in expected and 47.63% in best. Both are measured.
> - **Cost increases:** 3% a year in expected and 2% in best. This is our assumption, not data.
> - **Valuation inputs:** the 20% discount rate, 2% terminal growth and 4x multiple are also our assumptions, not data.
> - **Owner salary:** none is deducted. If you work unpaid, a buyer would likely deduct a market salary, which would lower the value.
> - **Tax:** a flat 17% is applied, so the figures are slightly conservative.
>
> The best case needs about a 10% sales rise and a 3-point margin improvement. Your measured trend is flat. I can rerun the model with your own growth or cost figures if you want.

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
| biz-straits | yes | 1 | `e5d88994615618722a2bf2f4b1a86c2734b0d90d1b6822d97bf9556d0b3a17a9` |

Claude usage for this case: 2 calls, about US$0.031.
