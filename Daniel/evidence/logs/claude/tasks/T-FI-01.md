# T-FI-01: Financing options for the forecast gap

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Compliance: every option shows total cost AND effective rate, and nothing implies approval. Cheapest fit is trade financing at S$172.58 total cost, 16.44% EIR.

## Conversation

### Turn 1

**User:**

> What financing options do we have?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `find_financing` |  | **ok** | ok |

<details><summary>Tool result data</summary>

`find_financing`

```json
{
  "value": {
    "need": {
      "need": {
        "amount": "13260.76",
        "target": "0",
        "draw_date": "2026-12-06",
        "repay_date": null,
        "duration_days": 22,
        "duration_months": 1,
        "duration_is_lower_bound": true,
        "purpose": "working capital: forecast cash gap",
        "basis": "after non-borrowing plan"
      },
      "source": "forecast",
      "plan_steps": [
        "Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10"
      ],
      "forecast_need": {
        "amount": "13260.76",
        "target": "0",
        "draw_date": "2026-12-06",
        "repay_date": null,
        "duration_days": 22,
        "duration_months": 1,
        "duration_is_lower_bound": true,
        "purpose": "working capital: forecast cash gap",
        "basis": "after non-borrowing plan"
      },
      "question": null,
      "message": "From your forecast: about S$13,260.76 from 2026-12-06 (after the steps without borrowing)."
    },
    "facts": [
      {
        "metric": "months_operating",
        "value": "99",
        "source": "incorporated on 2018-06-11"
      },
      {
        "metric": "annual_revenue",
        "value": "1661589.30",
        "source": "cash-basis sales receipts, 2025-10-01 to 2026-09-30"
      },
      {
        "metric": "gross_margin",
        "value": "0.5106",
        "source": "cash basis, last 12 months"
      },
      {
        "metric": "average_monthly_balance",
        "value": "138875.98",
        "source": "average of 6 month-end balances to 2026-09-30"
      },
      {
        "metric": "employee_count",
        "value": "14",
        "source": "business profile"
      },
      {
        "metric": "local_shareholding_pct",
        "value": "70",
        "source": "business profile"
      },
      {
        "metric": "registered_in_sg",
        "value": true,
        "source": "business profile"
      }
    ],
    "eligibility": [
      {
        "product_id": "wc-efs",
        "product_name": "SME Working Capital Loan (EFS-style)",
        "lender": "Harbourline Bank",
        "eligible": true,
        "rules": [
          {
            "description": "Registered and operating in Singapore",
            "metric": "registered_in_sg",
            "status": "pass",
            "reason": "registration: registered in Singapore; needs registered in Singapore"
          },
          {
            "description": "At least 30% local shareholding",
            "metric": "local_shareholding_pct",
            "status": "pass",
            "reason": "local shareholding: 70%; needs at least 30%"
          },
          {
            "description": "Operating for at least 12 months",
            "metric": "months_operating",
            "status": "pass",
            "reason": "time operating: 99 months; needs at least 12 months"
          },
          {
            "description": "At most 200 employees",
            "metric": "employee_count",
            "status": "pass",
            "reason": "employees: 14 staff; needs at most 200 staff"
          }
        ],
        "max_amount": "300000.00",
        "reasons": []
      },
      {
        "product_id": "micro",
        "product_name": "Micro Business Loan",
        "lender": "Harbourline Bank",
        "eligible": false,
        "rules": [
          {
            "description": "Registered and operating in Singapore",
            "metric": "registered_in_sg",
            "status": "pass",
            "reason": "registration: registered in Singapore; needs registered in Singapore"
          },
          {
            "description": "At most 10 employees",
            "metric": "employee_count",
            "status": "fail",
            "reason": "employees: 14 staff; needs at most 10 staff"
          },
          {
            "description": "Operating for at least 6 months",
            "metric": "months_operating",
            "status": "pass",
            "reason": "time operating: 99 months; needs at least 6 months"
          }
        ],
        "max_amount": "100000.00",
        "reasons": [
          "employees: 14 staff; needs at most 10 staff"
        ]
      },
      {
        "product_id": "term",
        "product_name": "Unsecured Business Term Loan",
        "lender": "Merlion Commerce Bank",
        "eligible": true,
        "rules": [
          {
            "description": "Operating for at least 2 years",
            "metric": "months_operating",
            "status": "pass",
            "reason": "time operating: 99 months; needs at least 24 months"
          },
          {
            "description": "Annual revenue of at least S$500,000",
            "metric": "annual_revenue",
            "status": "pass",
            "reason": "annual revenue: S$1,661,589.30; needs at least S$500,000.00"
          }
        ],
        "max_amount": "500000.00",
        "reasons": []
      },
      {
        "product_id": "invoice",
        "product_name": "Invoice Financing",
        "lender": "Tanjong Trade Finance",
        "eligible": true,
        "rules": [
          {
            "description": "Operating for at least 6 months",
            "metric": "months_operating",
            "status": "pass",
            "reason": "time operating: 99 months; needs at least 6 months"
          },
          {
            "description": "Annual revenue of at least S$200,000",
            "metric": "annual_revenue",
            "status": "pass",
            "reason": "annual revenue: S$1,661,589.30; needs at least S$200,000.00"
          }
        ],
        "max_amount": "149275.19",
        "reasons": []
      },
      {
        "product_id": "revolver",
        "product_name": "Revolving Credit Line",
        "lender": "Harbourline Bank",
        "eligible": true,
        "rules": [
          {
            "description": "Operating for at least 2 years",
            "metric": "months_operating",
            "status": "pass",
            "reason": "time operating: 99 months; needs at least 24 months"
          },
          {
            "description": "Average month-end bank balance of at least S$50,000",
            "metric": "average_monthly_balance",
            "status": "pass",
            "reason": "average month-end balance: S$138,875.98; needs at least S$50,000.00"
          }
        ],
        "max_amount": "150000.00",
        "reasons": []
      },
      {
        "product_id": "trade",
        "product_name": "Trade Financing (supplier payments)",
        "lender": "Merlion Commerce Bank",
        "eligible": true,
        "rules": [
          {
            "description": "Operating for at least 12 months",
            "metric": "months_operating",
            "status": "pass",
            "reason": "time operating: 99 months; needs at least 12 months"
          },
          {
            "description": "Gross margin of at least 10%",
            "metric": "gross_margin",
            "status": "pass",
            "reason": "gross margin: 51.1%; needs at least 10.0%"
          }
        ],
        "max_amount": "1000000.00",
        "reasons": []
      },
      {
        "product_id": "shortterm",
        "product_name": "Short-term Business Loan",
        "lender": "QuickCap Lending",
        "eligible": true,
        "rules": [
          {
            "description": "Operating for at least 6 months",
            "metric": "months_operating",
            "status": "pass",
            "reason": "time operating: 99 months; needs at least 6 months"
          },
          {
            "description": "Annual revenue of at least S$100,000",
            "metric": "annual_revenue",
            "status": "pass",
            "reason": "annual revenue: S$1,661,589.30; needs at least S$100,000.00"
          }
        ],
        "max_amount": "200000.00",
        "reasons": []
      }
    ],
    "ranked": [
      {
        "rank": 1,
        "quote": {
          "product_id": "trade",
          "product_name": "Trade Financing (supplier payments)",
          "lender": "Merlion Commerce Bank",
          "type": "trade_financing",
          "repayment": "interest_only_bullet",
          "need_amount": "13260.76",
          "amount": "13360.97",
          "upfront_fees": "100.21",
          "amount_received": "13260.76",
          "term_months": 1,
          "draw_date": "2026-12-06",
          "end_date": "2027-01-06",
          "flows": [
            {
              "date": "2026-12-06",
              "amount": "13360.97",
              "kind": "draw",
              "interest": "0",
              "principal": "13360.97"
            },
            {
              "date": "2026-12-06",
              "amount": "-100.21",
              "kind": "fee",
              "interest": "0",
              "principal": "0"
            },
            {
              "date": "2027-01-06",
              "amount": "-13433.34",
              "kind": "repayment",
              "interest": "72.37",
              "principal": "13360.97"
            }
          ],
          "total_interest": "72.37",
          "total_fees": "100.21",
          "total_cost": "172.58",
          "eir_pct": "16.44",
          "instalment": null,
          "flags": [
            "Borrow S$13,360.97 so that S$13,260.76 is left after fees.",
            "Your cash hasn't recovered by the end of the forecast, so you may need it for longer, and the cost would be higher."
          ],
          "notes": []
        },
        "keeps_cash_above_target": true,
        "lowest_with_loan": "0.00",
        "lowest_with_loan_date": "2026-12-27",
        "repayments_after_forecast": 1
      },
      {
        "rank": 2,
        "quote": {
          "product_id": "invoice",
          "product_name": "Invoice Financing",
          "lender": "Tanjong Trade Finance",
          "type": "invoice_financing",
          "repayment": "on_invoice_settlement",
          "need_amount": "13260.76",
          "amount": "13327.40",
          "upfront_fees": "66.64",
          "amount_received": "13260.76",
          "term_months": 1,
          "draw_date": "2026-12-06",
          "end_date": "2027-01-05",
          "flows": [
            {
              "date": "2026-12-06",
              "amount": "13327.40",
              "kind": "draw",
              "interest": "0",
              "principal": "13327.40"
            },
            {
              "date": "2026-12-06",
              "amount": "-66.64",
              "kind": "fee",
              "interest": "0",
              "principal": "0"
            },
            {
              "date": "2027-01-05",
              "amount": "-13447.89",
              "kind": "repayment",
              "interest": "120.49",
              "principal": "13327.40"
            }
          ],
          "total_interest": "120.49",
          "total_fees": "66.64",
          "total_cost": "187.13",
          "eir_pct": "18.59",
          "instalment": null,
          "flags": [
            "Borrow S$13,327.40 so that S$13,260.76 is left after fees.",
            "Interest is charged for at least 30 days.",
            "Your cash hasn't recovered by the end of the forecast, so you may need it for longer, and the cost would be higher."
          ],
          "notes": []
        },
        "keeps_cash_above_target": true,
        "lowest_with_loan": "0.00",
        "lowest_with_loan_date": "2026-12-27",
        "repayments_after_forecast": 1
      },
      {
        "rank": 3,
        "quote": {
          "product_id": "revolver",
          "product_name": "Revolving Credit Line",
          "lender": "Harbourline Bank",
          "type": "revolving_credit",
          "repayment": "revolving",
          "need_amount": "13260.76",
          "amount": "13760.76",
          "upfront_fees": "500.00",
          "amount_received": "13260.76",
          "term_months": 1,
          "draw_date": "2026-12-06",
          "end_date": "2027-01-05",
          "flows": [
            {
              "date": "2026-12-06",
              "amount": "13760.76",
              "kind": "draw",
              "interest": "0",
              "principal": "13760.76"
            },
            {
              "date": "2026-12-06",
              "amount": "-500.00",
              "kind": "fee",
              "interest": "0",
              "principal": "0"
            },
            {
              "date": "2027-01-05",
              "amount": "-13868.21",
              "kind": "repayment",
              "interest": "107.45",
              "principal": "13760.76"
            }
          ],
          "total_interest": "107.45",
          "total_fees": "500.00",
          "total_cost": "607.45",
          "eir_pct": "72.45",
          "instalment": null,
          "flags": [
            "Borrow S$13,760.76 so that S$13,260.76 is left after fees.",
            "Interest is charged for at least 30 days.",
            "Your cash hasn't recovered by the end of the forecast, so you may need it for longer, and the cost would be higher."
          ],
          "notes": []
        },
        "keeps_cash_above_target": true,
        "lowest_with_loan": "0.00",
        "lowest_with_loan_date": "2026-12-27",
        "repayments_after_forecast": 1
      },
      {
        "rank": 4,
        "quote": {
          "product_id": "shortterm",
          "product_name": "Short-term Business Loan",
          "lender": "QuickCap Lending",
          "type": "working_capital_loan",
          "repayment": "amortising",
          "need_amount": "13260.76",
          "amount": "13670.89",
          "upfront_fees": "410.13",
          "amount_received": "13260.76",
          "term_months": 3,
          "draw_date": "2026-12-06",
          "end_date": "2027-03-06",
          "flows": [
            {
              "date": "2026-12-06",
              "amount": "13670.89",
              "kind": "draw",
              "interest": "0",
              "principal": "13670.89"
            },
            {
              "date": "2026-12-06",
              "amount": "-410.13",
              "kind": "fee",
              "interest": "0",
              "principal": "0"
            },
            {
              "date": "2027-01-06",
              "amount": "-4721.01",
              "kind": "repayment",
              "interest": "164.05",
              "principal": "4556.96"
            },
            {
              "date": "2027-02-06",
              "amount": "-4721.01",
              "kind": "repayment",
              "interest": "164.05",
              "principal": "4556.96"
            },
            {
              "date": "2027-03-06",
              "amount": "-4721.02",
              "kind": "repayment",
              "interest": "164.05",
              "principal": "4556.97"
            }
          ],
          "total_interest": "492.15",
          "total_fees": "410.13",
          "total_cost": "902.28",
          "eir_pct": "48.58",
          "instalment": "4721.01",
          "flags": [
            "Borrow S$13,670.89 so that S$13,260.76 is left after fees.",
            "Shortest term is 3 months; you need about 1.",
            "Your cash hasn't recovered by the end of the forecast, so you may need it for longer, and the cost would be higher."
          ],
          "notes": []
        },
        "keeps_cash_above_target": true,
        "lowest_with_loan": "0.00",
        "lowest_with_loan_date": "2026-12-27",
        "repayments_after_forecast": 3
      },
      {
        "rank": 5,
        "quote": {
          "product_id": "wc-efs",
          "product_name": "SME Working Capital Loan (EFS-style)",
          "lender": "Harbourline Bank",
          "type": "working_capital_loan",
          "repayment": "amortising",
          "need_amount": "13260.76",
          "amount": "20000.00",
          "upfront_fees": "200.00",
          "amount_received": "19800.00",
          "term_months": 12,
          "draw_date": "2026-12-06",
          "end_date": "2027-12-06",
          "flows": [
            {
              "date": "2026-12-06",
              "amount": "20000.00",
              "kind": "draw",
              "interest": "0",
              "principal": "20000.00"
            },
            {
              "date": "2026-12-06",
              "amount": "-200.00",
              "kind": "fee",
              "interest": "0",
              "principal": "0"
            },
            {
              "date": "2027-01-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "125.00",
              "principal": "1610.15"
            },
            {
              "date": "2027-02-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "114.94",
              "principal": "1620.21"
            },
            {
              "date": "2027-03-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "104.81",
              "principal": "1630.34"
            },
            {
              "date": "2027-04-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "94.62",
              "principal": "1640.53"
            },
            {
              "date": "2027-05-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "84.37",
              "principal": "1650.78"
            },
            {
              "date": "2027-06-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "74.05",
              "principal": "1661.10"
            },
            {
              "date": "2027-07-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "63.67",
              "principal": "1671.48"
            },
            {
              "date": "2027-08-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "53.22",
              "principal": "1681.93"
            },
            {
              "date": "2027-09-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "42.71",
              "principal": "1692.44"
            },
            {
              "date": "2027-10-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "32.13",
              "principal": "1703.02"
            },
            {
              "date": "2027-11-06",
              "amount": "-1735.15",
              "kind": "repayment",
              "interest": "21.49",
              "principal": "1713.66"
            },
            {
              "date": "2027-12-06",
              "amount": "-1735.14",
              "kind": "repayment",
              "interest": "10.78",
              "principal": "1724.36"
            }
          ],
          "total_interest": "821.79",
          "total_fees": "200.00",
          "total_cost": "1021.79",
          "eir_pct": "9.82",
          "instalment": "1735.15",
          "flags": [
            "Minimum loan is S$20,000.00: you'd borrow S$6,539.24 more than you need.",
            "Shortest term is 12 months; you need about 1.",
            "Your cash hasn't recovered by the end of the forecast, so you may need it for longer, and the cost would be higher."
          ],
          "notes": [
            "Early repayment fee: 1% of the amount repaid early."
          ]
        },
        "keeps_cash_above_target": true,
        "lowest_with_loan": "6539.24",
        "lowest_with_loan_date": "2026-12-27",
        "repayments_after_forecast": 12
      },
      {
        "rank": 6,
        "quote": {
          "product_id": "term",
          "product_name": "Unsecured Business Term Loan",
          "lender": "Merlion Commerce Bank",
          "type": "term_loan",
          "repayment": "amortising",
          "need_amount": "13260.76",
          "amount": "50000.00",
          "upfront_fees": "1000.00",
          "amount_received": "49000.00",
          "term_months": 12,
          "draw_date": "2026-12-06",
          "end_date": "2027-12-06",
          "flows": [
            {
              "date": "2026-12-06",
              "amount": "50000.00",
              "kind": "draw",
              "interest": "0",
              "principal": "50000.00"
            },
            {
              "date": "2026-12-06",
              "amount": "-1000.00",
              "kind": "fee",
              "interest": "0",
              "principal": "0"
            },
            {
              "date": "2027-01-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-02-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-03-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-04-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-05-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-06-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-07-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-08-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-09-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-10-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-11-06",
              "amount": "-4395.84",
              "kind": "repayment",
              "interest": "229.17",
              "principal": "4166.67"
            },
            {
              "date": "2027-12-06",
              "amount": "-4395.76",
              "kind": "repayment",
              "interest": "229.13",
              "principal": "4166.63"
            }
          ],
          "total_interest": "2750.00",
          "total_fees": "1000.00",
          "total_cost": "3750.00",
          "eir_pct": "14.77",
          "instalment": "4395.84",
          "flags": [
            "Minimum loan is S$50,000.00: you'd borrow S$35,739.24 more than you need.",
            "Shortest term is 12 months; you need about 1.",
            "Your cash hasn't recovered by the end of the forecast, so you may need it for longer, and the cost would be higher."
          ],
          "notes": [
            "Early repayment fee: 3% of the amount repaid early."
          ]
        },
        "keeps_cash_above_target": true,
        "lowest_with_loan": "22717.65",
        "lowest_with_loan_date": "2026-11-20",
        "repayments_after_forecast": 12
      }
    ],
    "volatile": true,
    "disclaimer": "Approval is the lender's decision; these are illustrative terms, not offers. Illustrative catalogue for the demo. Lenders are fictional; products are modelled on common Singapore SME financing types (including Enterprise Financing Scheme-style working capital loans). Rates and fees are plausible examples, not quotes or offers. Approval is always the lender's decision.",
    "message": "<untrusted>From your forecast: about S$13,260.76 from 2026-12-06 (after the steps without borrowing). Best fit: Trade Financing (supplier payments) from Merlion Commerce Bank. Borrow S$13,360.97 for 1 month: total cost S$172.58, effective annual rate 16.44%. It keeps cash above S$0.00 for the whole 13-week forecast. This assumes the steps without borrowing are taken first: Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10. 5 other option(s) shown; 1 product(s) not eligible. Approval is the lender's decision; these are illustrative terms, not offers.</untrusted>"
  },
  "drivers": [],
  "data_coverage": {
    "period_start": "2025-10-01",
    "period_end": "2026-09-30",
    "record_count": 206
  },
  "warnings": [
    "Repayments after the 13-week forecast aren't checked against your cash; make sure the business can meet them."
  ]
}
```

</details>

**Assistant:**

> **You may not need to borrow much.** The forecast shows a gap of about S$13,260.76 from 2026-12-06, and that figure assumes you first chase invoice INV-1062 (Bayfront Grocers, S$51,283.20). If Bayfront pays by 2026-10-19 instead of 2026-11-10, the gap shrinks to that amount. The gap is expected to last about a month, possibly longer, because cash hasn't recovered by the end of the forecast.
>
> **Options, ranked by cost for this need:**
>
> | # | Product | Borrow | Total cost | EIR |
> |---|---|---|---|---|
> | 1 | Trade Financing (Merlion Commerce Bank), 1 month | S$13,360.97 | S$172.58 | 16.44% |
> | 2 | Invoice Financing (Tanjong Trade Finance), 1 month | S$13,327.40 | S$187.13 | 18.59% |
> | 3 | Revolving Credit Line (Harbourline Bank), 1 month | S$13,760.76 | S$607.45 | 72.45% |
> | 4 | Short-term Loan (QuickCap Lending), 3 months | S$13,670.89 | S$902.28 | 48.58% |
> | 5 | SME Working Capital Loan (Harbourline Bank), 12 months | S$20,000.00 (minimum) | S$1,021.79 | 9.82% |
> | 6 | Unsecured Term Loan (Merlion Commerce Bank), 12 months | S$50,000.00 (minimum) | S$3,750.00 | 14.77% |
>
> - **Not eligible:** the Micro Business Loan, because you have 14 staff and the limit is 10.
> - **Best fit:** Trade Financing has the lowest total cost and a 1-month term that matches the gap.
> - **Lowest rate, higher total cost:** the SME Working Capital Loan has the lowest EIR, but it has a S$20,000 minimum and a 12-month term. That means borrowing more than you need and paying more in total.
> - **Minimum loan sizes:** options 5 and 6 would leave you borrowing S$6,539.24 and S$35,739.24 more than you need.
> - **Repayments after the forecast:** the 13-week forecast doesn't check them, so make sure you can meet them.
> - **Approval:** it's the lender's decision, and these are illustrative terms, not offers.
>
> I can draft a reminder to Bayfront for INV-1062 or pre-fill an application. Which would you like?

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 1.

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
| biz-straits | yes | 1 | `503bc70fcbeffab889c2b534581bf6c9983bcf2cb4af11fa7d4d1a33cbe4b1aa` |

Claude usage for this case: 2 calls, about US$0.033.
