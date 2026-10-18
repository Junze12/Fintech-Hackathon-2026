# T-AN-10: Net profit over the last 12 months (accrual)

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** The headline profit question. On accrual basis Straits Harbour lost S$22,467.49 over the 12 months to September 2026 (operating margin about -1.0%), although its cash-basis operating margin was +6.2%. The answer must come from the accrual statements.

## Conversation

### Turn 1

**User:**

> Did we make a profit over the last 12 months? What was our net profit?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_financial_statements` | {"period": "last_12_months", "statement": "pnl"} | **ok** | ok |

<details><summary>Tool result data</summary>

`get_financial_statements`

```json
{
  "value": {
    "basis": "accrual",
    "view": "with_adjustments",
    "period": "12 months to Sep 2026",
    "start": "2025-10-01",
    "end": "2026-09-30",
    "months": [
      "2025-10",
      "2025-11",
      "2025-12",
      "2026-01",
      "2026-02",
      "2026-03",
      "2026-04",
      "2026-05",
      "2026-06",
      "2026-07",
      "2026-08",
      "2026-09"
    ],
    "pnl": {
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
    "balance_sheet": null,
    "cash_flow": null,
    "checks": {
      "balance_sheet_difference": "0.00",
      "closing_cash_minus_bank": "0.00",
      "balanced": true,
      "cash_matches_bank": true
    },
    "ratios": {
      "gross_margin": "0.4937",
      "operating_margin": "-0.0103",
      "net_margin": "-0.0147",
      "ebitda": "3747.26",
      "current_ratio": "2.06",
      "debt_ratio": "0.4819"
    },
    "fixed_assets": [],
    "loans": [],
    "monthly": [],
    "adjustments": null
  },
  "drivers": [
    {
      "label": "<untrusted>Payroll (gross pay + employer CPF)</untrusted>",
      "amount": "562839.88",
      "detail": "<untrusted>operating expense</untrusted>"
    },
    {
      "label": "<untrusted>Rent</untrusted>",
      "amount": "150000.00",
      "detail": "<untrusted>operating expense</untrusted>"
    },
    {
      "label": "<untrusted>Utilities</untrusted>",
      "amount": "25086.46",
      "detail": "<untrusted>operating expense</untrusted>"
    },
    {
      "label": "<untrusted>Unpaid supplier bills</untrusted>",
      "amount": "108130.55",
      "detail": "<untrusted>cash released</untrusted>"
    },
    {
      "label": "<untrusted>Stock</untrusted>",
      "amount": "-73759.54",
      "detail": "<untrusted>cash tied up</untrusted>"
    },
    {
      "label": "<untrusted>Checks</untrusted>",
      "amount": null,
      "detail": "<untrusted>Balance sheet balances; closing cash matches the bank</untrusted>"
    }
  ],
  "data_coverage": {
    "period_start": "2025-10-01",
    "period_end": "2026-09-30",
    "record_count": 206
  },
  "warnings": [
    "Accrual basis: sales and costs count when invoiced or incurred, not when paid; amounts exclude GST",
    "10 uncategorised payment(s) are counted as other operating costs (real money out that no rule labelled)."
  ]
}
```

</details>

**Assistant:**

> No. Over the last 12 months (Oct 2025 to Sep 2026, accrual basis, excluding GST) the business made a small loss. Net profit was **–S$22,467.49**.
>
> - **Revenue:** S$1,523,644.43
> - **Gross profit:** S$752,221.35 (gross margin 49.37%)
> - **Operating expenses:** S$767,974.09. Payroll was S$562,839.88 and rent was S$150,000.00.
> - **Operating profit:** –S$15,752.74
> - **Interest:** S$6,714.75
> - **Net margin:** –1.47%
>
> Operating expenses were slightly higher than gross profit, and interest made the loss bigger. EBITDA was slightly positive at S$3,747.26.
>
> Ten uncategorised payments are counted as other operating costs. If some of them belong elsewhere, the figures could shift a little. I can list them if you want to check.

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
| biz-straits | yes | 1 | `ff65a9e8c882dcf00629aa5931908fd1e5bd550f61dadb1242dccb2fbaa746c5` |

Claude usage for this case: 2 calls, about US$0.019.
