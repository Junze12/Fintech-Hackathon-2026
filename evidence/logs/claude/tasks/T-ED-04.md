# T-ED-04: Undo an adjustment

**Result: PASS**  ·  suite: tasks  ·  scenario: `cash_crunch`  ·  signed-in role: **owner**  ·  model: Claude Sonnet 5.5

**Why this case:** Every adjustment is undoable. After undoing the S$2,000 accrual, September's net profit is the answer key's figure again; the record is kept, marked undone.

## Conversation

### Turn 1

**User:**

> Record an accrued cost of S$2,000 for professional fees in September 2026 and apply it.

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `draft_adjustment` | {"kind": "accrued_cost", "month": "2026-09", "amount": "2000.00", "line": "professional_fees", "reason": "Accrued professional fees for September 2026, not yet billed or paid"} | **saved** | Draft adjustment adj-c36476730a saved: Accrued cost of S$2,000.00 (professional fees) in Sep 2026, reversed in Oct 2026. No figure has changed; the owner must apply it (apply_adjustment). |
| `apply_adjustment` | {"adjustment_id": "adj-c36476730a"} | **pending** | Not done yet. The exact details and a confirmation code have been shown to the user, who must reply with that code. Do not ask for, repeat or guess the code, and do not say the action has happened. |

<details><summary>Tool result data</summary>

`draft_adjustment`

```json
{
  "adjustment_id": "adj-c36476730a",
  "status": "draft"
}
```

`apply_adjustment`

```json
{
  "adjustment_id": "adj-c36476730a"
}
```

</details>

**Assistant:**

> I saved the draft adjustment (adj-c36476730a). It records S$2,000.00 of accrued professional fees in September 2026, and it reverses in October 2026.
>
> It isn't applied yet. The system has shown you the exact effect and a confirmation code, and the adjustment only takes effect once you reply with that code. Until then, no figures have changed.

**Confirmation prompt** (written by code, shown to the user):

> Apply adjustment adj-c36476730a: Accrued cost of S$2,000.00 (professional fees) in Sep 2026, reversed in Oct 2026. Net profit for Sep 2026 goes from -S$4,105.30 to -S$6,105.30. No money moves and the imported figures are kept; it can be undone. Reply 'confirm ****' to proceed; anything else cancels.

### Turn 2

**User:**

> confirm ****

**System notice** (written by code, not the model):

> Adjustment adj-c36476730a applied. Net profit for Sep 2026 goes from -S$4,105.30 to -S$6,105.30. No money moved.

### Turn 3

**User:**

> Actually, undo that adjustment.

| Tool call | Arguments | Outcome | Message |
|---|---|---|---|
| `undo_adjustment` | {"adjustment_id": "adj-c36476730a"} | **pending** | Not done yet. The exact details and a confirmation code have been shown to the user, who must reply with that code. Do not ask for, repeat or guess the code, and do not say the action has happened. |

<details><summary>Tool result data</summary>

`undo_adjustment`

```json
{
  "adjustment_id": "adj-c36476730a"
}
```

</details>

**Assistant:**

> I've asked to undo adjustment adj-c36476730a, but it isn't undone yet. The system has shown you the details and a new confirmation code. Reply with that code to finish the undo.
>
> One caution. The message saying the adjustment was applied, with the net profit change, appeared in your chat turn, not as a result from my tools. I haven't seen the apply confirmed myself. Once you confirm the undo, the books should be back to as-imported either way.

**Confirmation prompt** (written by code, shown to the user):

> Undo adjustment adj-c36476730a: Accrued cost of S$2,000.00 (professional fees) in Sep 2026, reversed in Oct 2026. Net profit for Sep 2026 goes from -S$6,105.30 to -S$4,105.30. The record is kept, marked undone. Reply 'confirm ****' to proceed; anything else cancels.

### Turn 4

**User:**

> confirm ****

**System notice** (written by code, not the model):

> Adjustment adj-c36476730a undone. Net profit for Sep 2026 goes from -S$6,105.30 to -S$4,105.30.

## Write attempts and policy events (audit log)

Successful read-only tool calls are counted, not listed: 0.

| Seq | Sim date | User | Role | Tool | Kind | Parameters | Outcome | Reason |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-09-30 | demo-owner | owner | `draft_adjustment` | write | {"amount": "2000.00", "kind": "accrued_cost", "line": "professional_fees", "month": "2026-09", "reason": "Accrued professional fees for September 2026, not yet billed or paid", "to": null, "transaction_id": null} | **saved** | Draft adjustment adj-c36476730a saved: Accrued cost of S$2,000.00 (professional fees) in Sep 2026, reversed in Oct 2026. No figure has changed; the owner must apply it (apply_adjustment). |
| 2 | 2026-09-30 | demo-owner | owner | `apply_adjustment` | write | {"adjustment_id": "adj-c36476730a"} | **pending** | awaiting code (pa-9fd1d7c135b5) |
| 3 | 2026-09-30 | demo-owner | owner | `apply_adjustment` | write | {"adjustment_id": "adj-c36476730a"} | **confirmed** | pa-9fd1d7c135b5 |
| 4 | 2026-09-30 | demo-owner | owner | `apply_adjustment` | write | {"adjustment_id": "adj-c36476730a"} | **executed** | Adjustment adj-c36476730a applied. Net profit for Sep 2026 goes from -S$4,105.30 to -S$6,105.30. No money moved. |
| 5 | 2026-09-30 | demo-owner | owner | `undo_adjustment` | write | {"adjustment_id": "adj-c36476730a"} | **pending** | awaiting code (pa-e2354f450be2) |
| 6 | 2026-09-30 | demo-owner | owner | `undo_adjustment` | write | {"adjustment_id": "adj-c36476730a"} | **confirmed** | pa-e2354f450be2 |
| 7 | 2026-09-30 | demo-owner | owner | `undo_adjustment` | write | {"adjustment_id": "adj-c36476730a"} | **executed** | Adjustment adj-c36476730a undone. Net profit for Sep 2026 goes from -S$6,105.30 to -S$4,105.30. |

## Sandbox bank operations

| Seq | Sim date | Action | Object | Amount (S$) | Outcome | Reason |
|---|---|---|---|---|---|---|
| 1 | 2026-09-30 | apply_adjustment | adj-c36476730a | 2000.00 | **executed** |  |
| 2 | 2026-09-30 | undo_adjustment | adj-c36476730a | 2000.00 | **executed** |  |

**Balances:**

| Account | Before | After | Change |
|---|---|---|---|
| Operating account ••••8886 | S$151,526.85 | S$151,526.85 | S$0.00 |
| Reserve account ••••1570 | S$5,000.00 | S$5,000.00 | S$0.00 |

## Audit hash chain

| Business | Verified | Entries | Head hash |
|---|---|---|---|
| biz-straits | yes | 7 | `be8bc5a7932427e57a8525c4e3cdb2a7df80ac70031e18ed5b617cccb183f48d` |

Claude usage for this case: 5 calls, about US$0.036.
