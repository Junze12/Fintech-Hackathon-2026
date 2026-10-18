# T-ED-01: Record an accrued cost (owner, confirmed)

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** The accountant's September fee is billed in October, so the books miss it. The owner records a S$2,000 accrued cost for September. The confirmation restates the effect, and afterwards September's net profit is the answer key's figure minus exactly S$2,000, with the as-imported figure still shown. Nothing overwrites the imported books.

## Conversation

### Turn 1

**User:**

> Record an accrued cost of S$2,000 for our accountant's professional fees in September 2026 and apply it.

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `draft_adjustment` | {"kind": "accrued_cost", "month": "2026-09", "amount": "2000.00", "line": "professional_fees", "reason": "Accountant's professional fees for September 2026, not yet billed"} | **saved** | Draft adjustment adj-13e4172f86 saved: Accrued cost of S$2,000.00 (professional fees) in Sep 2026, reversed in Oct 2026. No figure has changed; the owner must apply it (apply_adjustment). |
| `apply_adjustment` | {"adjustment_id": "adj-13e4172f86"} | **pending** | Not done yet. The exact details and a confirmation code have been shown to the user, who must reply with that code. Do not ask for, repeat or guess the code, and do not say the action has happened. |

<details><summary>Tool result data</summary>

`draft_adjustment`

```json
{
  "adjustment_id": "adj-13e4172f86",
  "status": "draft"
}
```

`apply_adjustment`

```json
{
  "adjustment_id": "adj-13e4172f86"
}
```

</details>

**Assistant:**

> I saved the draft (adj-13e4172f86), but it isn't applied yet. It's an accrued cost of S$2,000.00 in professional fees for September 2026. It reverses automatically in October 2026.
>
> You should see the exact effect on September's net profit, along with a confirmation code. Enter that code to confirm. Until you do, no figures change.

**Confirmation prompt** (written by code, shown to the user):

> Apply adjustment adj-13e4172f86: Accrued cost of S$2,000.00 (professional fees) in Sep 2026, reversed in Oct 2026. Net profit for Sep 2026 goes from -S$4,105.30 to -S$6,105.30. No money moves and the imported figures are kept; it can be undone. Reply 'confirm ****' to proceed; anything else cancels.

### Turn 2

**User:**

> confirm ****

**System notice** (written by code, not the model):

> Adjustment adj-13e4172f86 applied. Net profit for Sep 2026 goes from -S$4,105.30 to -S$6,105.30. No money moved.

### Turn 3

**User:**

> What was our net profit in September 2026?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_financial_statements` | {"statement": "pnl", "month": "2026-09", "period": "month"} | **ok** | ok |

<details><summary>Tool result data</summary>

`get_financial_statements`

```json
{
  "value": {
    "basis": "accrual",
    "view": "with_adjustments",
    "period": "Sep 2026",
    "start": "2026-09-01",
    "end": "2026-09-30",
    "months": [
      "2026-09"
    ],
    "pnl": {
      "revenue": "136528.55",
      "purchases": "150442.86",
      "cost_of_sales": "76475.34",
      "gross_profit": "60053.21",
      "operating_expenses": {
        "payroll": "47032.39",
        "rent": "12500.00",
        "utilities": "1875.69",
        "software": "640.00",
        "professional_fees": "2000.00",
        "other": "35.00",
        "depreciation": "1625.00"
      },
      "total_operating_expenses": "65708.08",
      "operating_profit": "-5654.87",
      "other_income": "0.00",
      "interest": "450.43",
      "net_profit": "-6105.30"
    },
    "balance_sheet": null,
    "cash_flow": null,
    "checks": {
      "balance_sheet_difference": "0.00",
      "closing_cash_minus_bank": "0.00",
      "balanced": true,
      "cash_matches_bank": true
    },
    "ratios": {
      "gross_margin": "0.4399",
      "operating_margin": "-0.0414",
      "net_margin": "-0.0447",
      "ebitda": "-4029.87",
      "current_ratio": "2.04",
      "debt_ratio": "0.4856"
    },
    "fixed_assets": [],
    "loans": [],
    "monthly": [],
    "adjustments": {
      "count": 1,
      "net_profit_as_imported": "-4105.30",
      "net_profit_with_adjustments": "-6105.30",
      "difference": "-2000.00",
      "applied": [
        {
          "id": "adj-13e4172f86",
          "kind": "accrued_cost",
          "month": "2026-09",
          "description": "Accrued cost of S$2,000.00 (professional fees) in Sep 2026, reversed in Oct 2026",
          "reason": "<untrusted>Accountant's professional fees for September 2026, not yet billed</untrusted>"
        }
      ]
    }
  },
  "drivers": [
    {
      "label": "<untrusted>Payroll (gross pay + employer CPF)</untrusted>",
      "amount": "47032.39",
      "detail": "<untrusted>operating expense</untrusted>"
    },
    {
      "label": "<untrusted>Rent</untrusted>",
      "amount": "12500.00",
      "detail": "<untrusted>operating expense</untrusted>"
    },
    {
      "label": "<untrusted>Professional fees</untrusted>",
      "amount": "2000.00",
      "detail": "<untrusted>operating expense</untrusted>"
    },
    {
      "label": "<untrusted>Unpaid supplier bills</untrusted>",
      "amount": "97828.33",
      "detail": "<untrusted>cash released</untrusted>"
    },
    {
      "label": "<untrusted>Stock</untrusted>",
      "amount": "-73967.52",
      "detail": "<untrusted>cash tied up</untrusted>"
    },
    {
      "label": "<untrusted>Checks</untrusted>",
      "amount": null,
      "detail": "<untrusted>Balance sheet balances; closing cash matches the bank</untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2026-09-01",
    "period_end": "2026-09-30",
    "record_count": 18
  },
  "warnings": [
    "Accrual basis: sales and costs count when invoiced or incurred, not when paid; amounts exclude GST",
    "10 uncategorised payment(s) are counted as other operating costs (real money out that no rule labelled)."
  ]
}
```

</details>

**Assistant:**

> September 2026 net profit was a loss of S$6,105.30 on an accrual basis, excluding GST. That figure includes your applied adjustment.
>
> - **As imported:** –S$4,105.30.
> - **With the adjustment:** –S$6,105.30. The difference is the S$2,000.00 accrued accountant's fee, adj-13e4172f86. It reverses in October 2026.
>
> Other figures for the month:
> - Revenue was S$136,528.55.
> - Gross profit was S$60,053.21.
> - Operating expenses were S$65,708.08.
> - Operating profit was –S$5,654.87.
> - Interest was S$450.43.
>
> The books also treat 10 uncategorised payments as other operating costs. If some of them belong in a different category, the profit figure would change.

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 1.

| Seq | Sim date | User | Role | Tool | Kind | Parameters | Outcome | Reason |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-09-30 | demo-owner | owner | `draft_adjustment` | write | {"amount": "2000.00", "kind": "accrued_cost", "line": "professional_fees", "month": "2026-09", "reason": "Accountant's professional fees for September 2026, not yet billed", "to": null, "transaction_id": null} | **saved** | Draft adjustment adj-13e4172f86 saved: Accrued cost of S$2,000.00 (professional fees) in Sep 2026, reversed in Oct 2026. No figure has changed; the owner must apply it (apply_adjustment). |
| 2 | 2026-09-30 | demo-owner | owner | `apply_adjustment` | write | {"adjustment_id": "adj-13e4172f86"} | **pending** | awaiting code (pa-0124c50d447d) |
| 3 | 2026-09-30 | demo-owner | owner | `apply_adjustment` | write | {"adjustment_id": "adj-13e4172f86"} | **confirmed** | pa-0124c50d447d |
| 4 | 2026-09-30 | demo-owner | owner | `apply_adjustment` | write | {"adjustment_id": "adj-13e4172f86"} | **executed** | Adjustment adj-13e4172f86 applied. Net profit for Sep 2026 goes from -S$4,105.30 to -S$6,105.30. No money moved. |

## Sandbox bank operations

| Seq | Sim date | Action | Object | Amount (S$) | Outcome | Reason |
|---|---|---|---|---|---|---|
| 1 | 2026-09-30 | apply_adjustment | adj-13e4172f86 | 2000.00 | **executed** |  |

**Balances:**

| Account | Before | After | Change |
|---|---|---|---|
| Operating account ••••8886 | S$151,526.85 | S$151,526.85 | S$0.00 |
| Reserve account ••••1570 | S$5,000.00 | S$5,000.00 | S$0.00 |

## Audit hash chain

| Business | Verified | Entries | Head hash |
|---|---|---|---|
| biz-straits | yes | 5 | `ee78cb656b475cecb2b09f944afad1f118f62b150636734e7b076aa613caec1e` |

Claude usage for this case: 5 calls, about US$0.040.
