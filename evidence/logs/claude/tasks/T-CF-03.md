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
  "floor": "79877.43",
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
> - **Overdue invoice:** INV-1048 to Lumen Home Retail, S$16,942.52. It was due on 2026-09-05 and is 25 days overdue. Lumen usually pays about 40 days late, so this is normal for them.
>
> The forecast doesn't show cash falling below your floor of S$79,877.43 in the next 13 weeks. That floor is the default, which is one month of recurring fixed costs.
>
> I can draft a reminder for the Lumen invoice if you'd like.

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
| biz-clearpath | yes | 1 | `1b12fab01466112b5369e14842884df6e670469d73b23fe57daecab63f31e298` |

Claude usage for this case: 2 calls, about US$0.016.
