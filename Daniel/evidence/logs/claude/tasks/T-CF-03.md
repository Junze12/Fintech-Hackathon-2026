# T-CF-03: Alerts on the healthy business

**Result: PASS**  ·  suite: tasks  ·  scenario: `concentrated_b2b`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Only one alert, an overdue invoice from a customer who always pays late.

## Conversation

### Turn 1

**User:**

> Any alerts?

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `get_alerts` |  | **ok** | ok |

<details><summary>Tool result data</summary>

`get_alerts`

```json
{
  "floor": "74381.42",
  "floor_source": "default",
  "alerts": {
    "value": [
      {
        "key": "<untrusted>overdue:i-0048</untrusted>",
        "kind": "overdue_receivable",
        "severity": "info",
        "title": "<untrusted>Invoice INV-1048 is 25 days overdue</untrusted>",
        "message": "<untrusted>Invoice INV-1048 to Lumen Home Retail: S$16,942.52 was due on 2026-09-05 and is 25 days overdue. Lumen Home Retail usually pays about 40 days late, so this is normal for them.</untrusted>",
        "impact": "16942.52",
        "event_date": "2026-09-05",
        "days_away": 0,
        "score": "16942.52",
        "drivers": []
      }
    ],
    "drivers": [],
    "data_coverage": {
      "period_start": "2025-10-01",
      "period_end": "2026-09-30",
      "record_count": 193
    },
    "warnings": []
  }
}
```

</details>

**Assistant:**

> You have one alert, and it's low severity (info).
>
> - **Overdue invoice:** INV-1048 to Lumen Home Retail, S$16,942.52. It was due 2026-09-05 and is 25 days overdue. Lumen usually pays about 40 days late, so this is normal for them.
>
> No cash-floor or payment-shortfall alerts came up. The floor used is S$74,381.42, which is the default (one month of recurring fixed costs) and not one you set.
>
> I can draft a reminder to Lumen if you'd like.

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 1.

None: no write was attempted.

## Sandbox bank operations

None: the sandbox bank was not asked to move or record any money.

**Balances:**

| Account | Before | After | Change |
|---|---|---|---|
| Operating account ••••6943 | S$171,591.05 | S$171,591.05 | S$0.00 |
| Reserve account ••••1490 | S$90,000.00 | S$90,000.00 | S$0.00 |

## Audit hash chain

| Business | Verified | Entries | Head hash |
|---|---|---|---|
| biz-clearpath | yes | 1 | `de5716c80a308d33cbed2ac7902159fdf194977a1c6e8425243b655cae4a56ca` |

Claude usage for this case: 2 calls, about US$0.009.
