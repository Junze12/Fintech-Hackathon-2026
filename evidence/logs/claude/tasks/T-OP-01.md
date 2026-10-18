# T-OP-01: Which plan gets a struggling business safely through 13 weeks

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** No plan without borrowing survives: the 27 Dec payroll leaves Straits Harbour short in every run. compare_options scores 56 plans on the stress test's 2,000 runs; the best one chases INV-1062, asks Meridian to wait on MFI-88120 and opens a S$29,000 credit line drawn only when short: 96.10% of runs stay above zero for about S$521.98 (S$500 fee + interest). The answer must name the credit line and give survival and cost from the tool.

## Conversation

### Turn 1

**User:**

> Which plan gets us safely through the next three months, and what would it cost?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `compare_options` |  | **ok** | ok |

<details><summary>Tool result data</summary>

`compare_options`

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
    "risk_day": "2026-11-05",
    "levers": {
      "chase_on_time_pct": 50,
      "customer_loss_pct": 0,
      "discount_pct": "2",
      "discount_days": 10,
      "discount_accept_pct": 50
    },
    "options": [
      {
        "key": "collect:i-0062",
        "kind": "collect",
        "title": "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>",
        "assumption": "Assumes a 50% chance the customer pays by the due date once chased (our assumption, not data); otherwise it pays as it usually does.",
        "follow_up_tool": "draft_reminder"
      },
      {
        "key": "reschedule:b-bulk-stock",
        "kind": "reschedule",
        "title": "<untrusted>Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19</untrusted>",
        "assumption": "Needs the supplier's agreement; a late payment may cost a fee or an early-payment discount.",
        "follow_up_tool": null
      },
      {
        "key": "discount",
        "kind": "discount",
        "title": "<untrusted>Offer 2% off every open invoice paid within 10 days</untrusted>",
        "assumption": "Assumes each customer takes it with a 50% chance (our assumption, not data). Invoices the same plan chases are left out.",
        "follow_up_tool": null
      }
    ],
    "financing": [
      {
        "key": "loan:wc-efs",
        "kind": "loan",
        "product_id": "wc-efs",
        "name": "SME Working Capital Loan (EFS-style)",
        "lender": "Harbourline Bank",
        "offered": true,
        "reason": null
      },
      {
        "key": "loan:micro",
        "kind": "loan",
        "product_id": "micro",
        "name": "Micro Business Loan",
        "lender": "Harbourline Bank",
        "offered": false,
        "reason": "employees: 14 staff; needs at most 10 staff"
      },
      {
        "key": "loan:term",
        "kind": "loan",
        "product_id": "term",
        "name": "Unsecured Business Term Loan",
        "lender": "Merlion Commerce Bank",
        "offered": true,
        "reason": null
      },
      {
        "key": "loan:invoice",
        "kind": "loan",
        "product_id": "invoice",
        "name": "Invoice Financing",
        "lender": "Tanjong Trade Finance",
        "offered": true,
        "reason": null
      },
      {
        "key": "line",
        "kind": "credit_line",
        "product_id": "revolver",
        "name": "Revolving Credit Line",
        "lender": "Harbourline Bank",
        "offered": true,
        "reason": null
      },
      {
        "key": "loan:trade",
        "kind": "loan",
        "product_id": "trade",
        "name": "Trade Financing (supplier payments)",
        "lender": "Merlion Commerce Bank",
        "offered": true,
        "reason": null
      },
      {
        "key": "loan:shortterm",
        "kind": "loan",
        "product_id": "shortterm",
        "name": "Short-term Business Loan",
        "lender": "QuickCap Lending",
        "offered": true,
        "reason": null
      }
    ],
    "plans_compared": 56,
    "best": {
      "key": "collect:i-0062+reschedule:b-bulk-stock+line",
      "rank": 1,
      "actions": [
        "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>",
        "<untrusted>Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19</untrusted>",
        "<untrusted>Open a S$29,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>"
      ],
      "option_keys": [
        "collect:i-0062",
        "reschedule:b-bulk-stock"
      ],
      "financing_key": "line",
      "survival_pct": "96.10",
      "meets_target": true,
      "mean_days_survived": "87.1",
      "cost_vs_nothing": "521.98",
      "cost_parts": [
        {
          "key": "discounts",
          "label": "Discounts given",
          "amount": "0.00"
        },
        {
          "key": "fees",
          "label": "Financing fees",
          "amount": "500.00"
        },
        {
          "key": "interest",
          "label": "Interest",
          "amount": "21.98"
        },
        {
          "key": "lost_customers",
          "label": "Lost customers (12 months' gross profit)",
          "amount": "0.00"
        }
      ],
      "low_point": "0.00",
      "low_point_date": "2026-12-06",
      "gap_on_risk_day": "0.00",
      "most_likely_failure_day": "2026-12-06",
      "extra_buffer": "0.00",
      "credit_line": {
        "product_id": "revolver",
        "limit": "29000.00",
        "needed_for_target": "28830.60",
        "capped": false,
        "runs_drawing_pct": "100.00",
        "drawn_at_end_p50": "13525.81",
        "drawn_at_end_p90": "13530.15"
      },
      "loan": null,
      "customer_loss": [],
      "follow_up_tools": [
        "draft_reminder",
        "prefill_application"
      ]
    },
    "table": [
      {
        "key": "nothing",
        "name": "<untrusted>Do nothing</untrusted>",
        "survival_pct": "0.00",
        "meets_target": false,
        "cost_vs_nothing": "0.00",
        "gap_on_risk_day": "48533.79",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "collect:i-0062",
        "name": "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>",
        "survival_pct": "0.00",
        "meets_target": false,
        "cost_vs_nothing": "0.00",
        "gap_on_risk_day": "37291.21",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "reschedule:b-bulk-stock",
        "name": "<untrusted>Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19</untrusted>",
        "survival_pct": "0.00",
        "meets_target": false,
        "cost_vs_nothing": "0.00",
        "gap_on_risk_day": "0.00",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "discount",
        "name": "<untrusted>Offer 2% off every open invoice paid within 10 days</untrusted>",
        "survival_pct": "0.00",
        "meets_target": false,
        "cost_vs_nothing": "1864.56",
        "gap_on_risk_day": "23325.25",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "loan:wc-efs",
        "name": "<untrusted>Borrow S$20,000.00 with SME Working Capital Loan (EFS-style) (Harbourline Bank) from 2026-11-05 for 12 months</untrusted>",
        "survival_pct": "45.70",
        "meets_target": false,
        "cost_vs_nothing": "1021.79",
        "gap_on_risk_day": "28733.79",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "loan:term",
        "name": "<untrusted>Borrow S$50,000.00 with Unsecured Business Term Loan (Merlion Commerce Bank) from 2026-11-05 for 12 months</untrusted>",
        "survival_pct": "93.40",
        "meets_target": false,
        "cost_vs_nothing": "3750.00",
        "gap_on_risk_day": "0.00",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "loan:invoice",
        "name": "<untrusted>Borrow S$13,091.27 with Invoice Financing (Tanjong Trade Finance) from 2026-11-05 for 2 months</untrusted>",
        "survival_pct": "25.00",
        "meets_target": false,
        "cost_vs_nothing": "274.56",
        "gap_on_risk_day": "35507.98",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "line",
        "name": "<untrusted>Open a S$50,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>",
        "survival_pct": "96.30",
        "meets_target": true,
        "cost_vs_nothing": "544.75",
        "gap_on_risk_day": "0.00",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "loan:trade",
        "name": "<untrusted>Borrow S$13,124.25 with Trade Financing (supplier payments) (Merlion Commerce Bank) from 2026-11-05 for 2 months</untrusted>",
        "survival_pct": "0.00",
        "meets_target": false,
        "cost_vs_nothing": "240.61",
        "gap_on_risk_day": "35507.97",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "loan:shortterm",
        "name": "<untrusted>Borrow S$13,428.68 with Short-term Business Loan (QuickCap Lending) from 2026-11-05 for 3 months</untrusted>",
        "survival_pct": "0.00",
        "meets_target": false,
        "cost_vs_nothing": "886.29",
        "gap_on_risk_day": "35507.97",
        "customer_loss": [],
        "recommended": false
      },
      {
        "key": "collect:i-0062+reschedule:b-bulk-stock+line",
        "name": "<untrusted>Best combination: Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10; Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19; Open a S$29,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>",
        "survival_pct": "96.10",
        "meets_target": true,
        "cost_vs_nothing": "521.98",
        "gap_on_risk_day": "0.00",
        "customer_loss": [],
        "recommended": true
      }
    ],
    "ranked": [
      {
        "key": "collect:i-0062+reschedule:b-bulk-stock+line",
        "rank": 1,
        "actions": [
          "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>",
          "<untrusted>Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19</untrusted>",
          "<untrusted>Open a S$29,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>"
        ],
        "option_keys": [
          "collect:i-0062",
          "reschedule:b-bulk-stock"
        ],
        "financing_key": "line",
        "survival_pct": "96.10",
        "meets_target": true,
        "mean_days_survived": "87.1",
        "cost_vs_nothing": "521.98",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "0.00"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "500.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "21.98"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "0.00",
        "low_point_date": "2026-12-06",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-12-06",
        "extra_buffer": "0.00",
        "credit_line": {
          "product_id": "revolver",
          "limit": "29000.00",
          "needed_for_target": "28830.60",
          "capped": false,
          "runs_drawing_pct": "100.00",
          "drawn_at_end_p50": "13525.81",
          "drawn_at_end_p90": "13530.15"
        },
        "loan": null,
        "customer_loss": [],
        "follow_up_tools": [
          "draft_reminder",
          "prefill_application"
        ]
      },
      {
        "key": "reschedule:b-bulk-stock+line",
        "rank": 2,
        "actions": [
          "<untrusted>Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19</untrusted>",
          "<untrusted>Open a S$29,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>"
        ],
        "option_keys": [
          "reschedule:b-bulk-stock"
        ],
        "financing_key": "line",
        "survival_pct": "96.10",
        "meets_target": true,
        "mean_days_survived": "87.1",
        "cost_vs_nothing": "522.35",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "0.00"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "500.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "22.35"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "0.00",
        "low_point_date": "2026-12-06",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-12-06",
        "extra_buffer": "0.00",
        "credit_line": {
          "product_id": "revolver",
          "limit": "29000.00",
          "needed_for_target": "28830.60",
          "capped": false,
          "runs_drawing_pct": "100.00",
          "drawn_at_end_p50": "13525.81",
          "drawn_at_end_p90": "13530.15"
        },
        "loan": null,
        "customer_loss": [],
        "follow_up_tools": [
          "prefill_application"
        ]
      },
      {
        "key": "collect:i-0062+line",
        "rank": 3,
        "actions": [
          "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>",
          "<untrusted>Open a S$46,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>"
        ],
        "option_keys": [
          "collect:i-0062"
        ],
        "financing_key": "line",
        "survival_pct": "96.25",
        "meets_target": true,
        "mean_days_survived": "86.2",
        "cost_vs_nothing": "533.71",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "0.00"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "500.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "33.71"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "0.00",
        "low_point_date": "2026-12-06",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-11-05",
        "extra_buffer": "0.00",
        "credit_line": {
          "product_id": "revolver",
          "limit": "46000.00",
          "needed_for_target": "45808.28",
          "capped": false,
          "runs_drawing_pct": "100.00",
          "drawn_at_end_p50": "13528.38",
          "drawn_at_end_p90": "13567.60"
        },
        "loan": null,
        "customer_loss": [],
        "follow_up_tools": [
          "draft_reminder",
          "prefill_application"
        ]
      },
      {
        "key": "line",
        "rank": 4,
        "actions": [
          "<untrusted>Open a S$50,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>"
        ],
        "option_keys": [],
        "financing_key": "line",
        "survival_pct": "96.30",
        "meets_target": true,
        "mean_days_survived": "86.3",
        "cost_vs_nothing": "544.75",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "0.00"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "500.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "44.75"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "0.00",
        "low_point_date": "2026-11-05",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-11-05",
        "extra_buffer": "0.00",
        "credit_line": {
          "product_id": "revolver",
          "limit": "50000.00",
          "needed_for_target": "49033.79",
          "capped": false,
          "runs_drawing_pct": "100.00",
          "drawn_at_end_p50": "13544.48",
          "drawn_at_end_p90": "13582.34"
        },
        "loan": null,
        "customer_loss": [],
        "follow_up_tools": [
          "prefill_application"
        ]
      },
      {
        "key": "collect:i-0062+reschedule:b-bulk-stock+discount+line",
        "rank": 5,
        "actions": [
          "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>",
          "<untrusted>Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19</untrusted>",
          "<untrusted>Offer 2% off every open invoice paid within 10 days</untrusted>",
          "<untrusted>Open a S$29,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>"
        ],
        "option_keys": [
          "collect:i-0062",
          "reschedule:b-bulk-stock",
          "discount"
        ],
        "financing_key": "line",
        "survival_pct": "95.00",
        "meets_target": true,
        "mean_days_survived": "86.7",
        "cost_vs_nothing": "1881.96",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "1357.37"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "500.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "24.59"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "0.00",
        "low_point_date": "2026-12-06",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-12-06",
        "extra_buffer": "0.00",
        "credit_line": {
          "product_id": "revolver",
          "limit": "29000.00",
          "needed_for_target": "28830.60",
          "capped": false,
          "runs_drawing_pct": "100.00",
          "drawn_at_end_p50": "14761.59",
          "drawn_at_end_p90": "15985.46"
        },
        "loan": null,
        "customer_loss": [],
        "follow_up_tools": [
          "draft_reminder",
          "prefill_application"
        ]
      },
      {
        "key": "collect:i-0062+discount+line",
        "rank": 6,
        "actions": [
          "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>",
          "<untrusted>Offer 2% off every open invoice paid within 10 days</untrusted>",
          "<untrusted>Open a S$47,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>"
        ],
        "option_keys": [
          "collect:i-0062",
          "discount"
        ],
        "financing_key": "line",
        "survival_pct": "95.50",
        "meets_target": true,
        "mean_days_survived": "86.5",
        "cost_vs_nothing": "1894.25",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "1357.37"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "500.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "36.88"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "0.00",
        "low_point_date": "2026-12-06",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-12-06",
        "extra_buffer": "0.00",
        "credit_line": {
          "product_id": "revolver",
          "limit": "47000.00",
          "needed_for_target": "46358.87",
          "capped": false,
          "runs_drawing_pct": "100.00",
          "drawn_at_end_p50": "14800.48",
          "drawn_at_end_p90": "15985.46"
        },
        "loan": null,
        "customer_loss": [],
        "follow_up_tools": [
          "draft_reminder",
          "prefill_application"
        ]
      },
      {
        "key": "reschedule:b-bulk-stock+discount+line",
        "rank": 7,
        "actions": [
          "<untrusted>Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19</untrusted>",
          "<untrusted>Offer 2% off every open invoice paid within 10 days</untrusted>",
          "<untrusted>Open a S$29,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>"
        ],
        "option_keys": [
          "reschedule:b-bulk-stock",
          "discount"
        ],
        "financing_key": "line",
        "survival_pct": "95.00",
        "meets_target": true,
        "mean_days_survived": "86.7",
        "cost_vs_nothing": "2390.11",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "1864.56"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "500.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "25.55"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "0.00",
        "low_point_date": "2026-12-06",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-12-06",
        "extra_buffer": "0.00",
        "credit_line": {
          "product_id": "revolver",
          "limit": "29000.00",
          "needed_for_target": "28882.07",
          "capped": false,
          "runs_drawing_pct": "100.00",
          "drawn_at_end_p50": "15427.16",
          "drawn_at_end_p90": "16455.02"
        },
        "loan": null,
        "customer_loss": [],
        "follow_up_tools": [
          "prefill_application"
        ]
      },
      {
        "key": "discount+line",
        "rank": 8,
        "actions": [
          "<untrusted>Offer 2% off every open invoice paid within 10 days</untrusted>",
          "<untrusted>Open a S$48,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short</untrusted>"
        ],
        "option_keys": [
          "discount"
        ],
        "financing_key": "line",
        "survival_pct": "96.05",
        "meets_target": true,
        "mean_days_survived": "86.5",
        "cost_vs_nothing": "2402.60",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "1864.56"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "500.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "38.04"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "0.00",
        "low_point_date": "2026-12-06",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-11-05",
        "extra_buffer": "0.00",
        "credit_line": {
          "product_id": "revolver",
          "limit": "48000.00",
          "needed_for_target": "47057.79",
          "capped": false,
          "runs_drawing_pct": "100.00",
          "drawn_at_end_p50": "15430.23",
          "drawn_at_end_p90": "16455.02"
        },
        "loan": null,
        "customer_loss": [],
        "follow_up_tools": [
          "prefill_application"
        ]
      },
      {
        "key": "loan:term",
        "rank": 9,
        "actions": [
          "<untrusted>Borrow S$50,000.00 with Unsecured Business Term Loan (Merlion Commerce Bank) from 2026-11-05 for 12 months</untrusted>"
        ],
        "option_keys": [],
        "financing_key": "loan:term",
        "survival_pct": "93.40",
        "meets_target": false,
        "mean_days_survived": "85.6",
        "cost_vs_nothing": "3750.00",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "0.00"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "1000.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "2750.00"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "31578.35",
        "low_point_date": "2026-12-27",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-12-06",
        "extra_buffer": "696.41",
        "credit_line": null,
        "loan": {
          "product_id": "term",
          "amount": "50000.00",
          "draw_date": "2026-11-05",
          "term_months": 12,
          "total_cost": "3750.00",
          "eir_pct": "14.80"
        },
        "customer_loss": [],
        "follow_up_tools": [
          "prefill_application"
        ]
      },
      {
        "key": "collect:i-0062+reschedule:b-bulk-stock+discount+loan:term",
        "rank": 10,
        "actions": [
          "<untrusted>Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10</untrusted>",
          "<untrusted>Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19</untrusted>",
          "<untrusted>Offer 2% off every open invoice paid within 10 days</untrusted>",
          "<untrusted>Borrow S$50,000.00 with Unsecured Business Term Loan (Merlion Commerce Bank) from 2026-12-06 for 12 months</untrusted>"
        ],
        "option_keys": [
          "collect:i-0062",
          "reschedule:b-bulk-stock",
          "discount"
        ],
        "financing_key": "loan:term",
        "survival_pct": "78.00",
        "meets_target": false,
        "mean_days_survived": "81.1",
        "cost_vs_nothing": "5107.37",
        "cost_parts": [
          {
            "key": "discounts",
            "label": "Discounts given",
            "amount": "1357.37"
          },
          {
            "key": "fees",
            "label": "Financing fees",
            "amount": "1000.00"
          },
          {
            "key": "interest",
            "label": "Interest",
            "amount": "2750.00"
          },
          {
            "key": "lost_customers",
            "label": "Lost customers (12 months' gross profit)",
            "amount": "0.00"
          }
        ],
        "low_point": "20246.38",
        "low_point_date": "2026-11-20",
        "gap_on_risk_day": "0.00",
        "most_likely_failure_day": "2026-11-27",
        "extra_buffer": "19046.18",
        "credit_line": null,
        "loan": {
          "product_id": "term",
          "amount": "50000.00",
          "draw_date": "2026-12-06",
          "term_months": 12,
          "total_cost": "3750.00",
          "eir_pct": "14.77"
        },
        "customer_loss": [],
        "follow_up_tools": [
          "draft_reminder",
          "prefill_application"
        ]
      }
    ],
    "frontier": [
      {
        "key": "collect:i-0062+reschedule:b-bulk-stock",
        "cost": "0.00",
        "survival_pct": "0.00"
      },
      {
        "key": "collect:i-0062+reschedule:b-bulk-stock+loan:trade",
        "cost": "169.52",
        "survival_pct": "48.35"
      },
      {
        "key": "collect:i-0062+reschedule:b-bulk-stock+line",
        "cost": "521.98",
        "survival_pct": "96.10"
      },
      {
        "key": "collect:i-0062+line",
        "cost": "533.71",
        "survival_pct": "96.25"
      },
      {
        "key": "line",
        "cost": "544.75",
        "survival_pct": "96.30"
      }
    ],
    "cost_bridge": [
      {
        "key": "fees",
        "label": "Financing fees",
        "kind": "up",
        "amount": "500.00",
        "start": "0",
        "end": "500.00"
      },
      {
        "key": "interest",
        "label": "Interest",
        "kind": "up",
        "amount": "21.98",
        "start": "500.00",
        "end": "521.98"
      },
      {
        "key": "total",
        "label": "Cost vs doing nothing",
        "kind": "total",
        "amount": "521.98",
        "start": "0",
        "end": "521.98"
      }
    ],
    "line_plan": "collect:i-0062+reschedule:b-bulk-stock+line",
    "line_daily": [],
    "best_daily": [],
    "message": "<untrusted>Best plan: Chase invoice INV-1062 (Bayfront Grocers Pte. Ltd., S$51,283.20) so it is paid by 2026-10-19 instead of 2026-11-10; Ask Meridian Food Imports Pte. Ltd. to accept payment of bill MFI-88120 (S$85,000.00) 14 days later, on 2026-11-19; Open a S$29,000.00 Revolving Credit Line (Harbourline Bank, 9.5% a year), drawn only when cash is short. With it 96.10% of runs stay above zero (doing nothing: 0.00%), costing about S$521.98 vs doing nothing.</untrusted>",
    "disclaimer": "Approval is the lender's decision; these are illustrative terms, not offers.",
    "assumptions": [
      "Every plan is run on the same 2,000 simulated runs as the stress test (same draw for the same customer payment). Survival = share of runs never below the floor; target 95%.",
      "Chasing an invoice: 50% chance it is paid by its due date (overdue: within 7 days), otherwise as the customer usually pays. Our assumption, not data.",
      "Discount offer: 2% off if paid within 10 days; each customer takes it with a 50% chance (our assumption, not data).",
      "Customer loss from chasing: off (0%) unless you set a chance.",
      "Credit line: the smallest limit (rounded up to S$1,000) that reaches the target, drawn at the end of a day when cash is below the floor and repaid when above it; interest daily on what is drawn, charged every 30 days; a run fails only when the line is used up. Interest after the forecast is not counted.",
      "Loans: priced like find_financing for the gap left by the plan's other steps; cost is the loan's whole-life interest and fees. Rescheduling a bill is counted as free, but the supplier may charge for it.",
      "'Low point' assumes every step works (chase paid on time, discount taken, nobody lost)."
    ]
  },
  "drivers": [
    {
      "label": "<untrusted>Financing fees</untrusted>",
      "amount": "500.00",
      "detail": "<untrusted>best plan's cost</untrusted>"
    },
    {
      "label": "<untrusted>Interest</untrusted>",
      "amount": "21.98",
      "detail": "<untrusted>best plan's cost</untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2025-10-01",
    "period_end": "2026-09-30",
    "record_count": 206
  },
  "warnings": [
    "In 1 run in 10 the credit line still has S$13,530.15 or more drawn at the end of the forecast; interest after that isn't counted."
  ]
}
```

</details>

**Assistant:**

> **Best plan:** it has three parts, and 96.10% of the 2,000 simulated runs stay above zero cash through 2026-12-27. Doing nothing survives in 0.00% of runs. The target is 95%.
>
> 1. **Chase INV-1062.** This is Bayfront Grocers, S$51,283.20. The aim is payment by 2026-10-19 instead of 2026-11-10.
> 2. **Ask Meridian Food Imports to accept bill MFI-88120 (S$85,000.00) 14 days later,** on 2026-11-19. They have to agree to this.
> 3. **Open a S$29,000.00 revolving credit line** with Harbourline Bank at 9.5% a year. You draw on it only when cash is short.
>
> **Cost versus doing nothing:** S$521.98. That is S$500.00 in financing fees and S$21.98 in interest. The plan has no discounts and no lost customers.
>
> **Caveats**
> - The chase assumes a 50% chance Bayfront pays on time once chased. That is our assumption, not data.
> - Rescheduling is counted as free. Meridian may charge a fee.
> - In 1 run in 10, at least S$13,530.15 is still drawn on the line at the end of the forecast. Interest after that isn't counted.
> - The line is an illustrative term, not an approval from the lender.
> - This is a simulation based on past payment habits. It is not a guarantee.
>
> **Alternatives**
> - **Credit line alone:** a S$50,000.00 line survives 96.30% of runs and costs S$544.75. It is simpler, but it needs a bigger line.
> - **Unsecured Business Term Loan:** S$50,000.00 survives 93.40% of runs, which misses the target. It costs S$3,750.00.
>
> Chasing and rescheduling alone don't get you through (0.00% survival). The credit line is what makes the plan work.
>
> I can draft the reminder to Bayfront or pre-fill the credit line application if you want.

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
| biz-straits | yes | 1 | `5a8c7ac6d35ec889a0c0be7e76c452d63a05893e9c6e8e791feacd7ead9481ce` |

Claude usage for this case: 2 calls, about US$0.047.
