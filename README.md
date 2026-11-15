# Snack Counter Automation

Automates the refill lifecycle for office snack counters in Oslo and Bengaluru:
from "box is empty" to "money back in your account", coordinated through the
company chat bot, with immediate HR claims and a monthly cross-office spend
report.

## Run

```bash
python3 test_snacks.py
```

No dependencies beyond Python 3.10+ (stdlib only). All 7 tests should pass.

## The refill lifecycle

```
OPEN -> ASSIGNED -> AWAITING_RECEIPT -> CLAIMED -> REIMBURSED
          | (24h deadline passes)
          +-> back to OPEN, reassigned to the next volunteer
```

1. **OPEN** — someone tells the bot the box is empty; the bot announces it and
   opens a refill request.
2. **ASSIGNED** — the bot picks one volunteer (fewest refills in the last 8
   weeks, holidays skipped) and sends a DM. Exactly one active commitment per
   request, so two people can never be tasked with the same refill. A pass or
   a 24h timeout rotates to someone else.
3. **Budget check BEFORE anyone spends** — the volunteer states an expected
   spend; if it would exceed the monthly budget (Oslo 6,000 NOK, Bengaluru
   15,000 INR), the bot suggests a smaller basket, waiting, or a one-tap
   manager override. Nobody is out of pocket for an unapproved spend.
4. **Over-estimate rule** — the volunteer is guaranteed the approved estimate.
   The HR claim carries the actual amount (true spend is recorded), flagged
   for HR review if the receipt is more than 10% over the estimate.
5. **CLAIMED** — the claim is submitted to HR immediately, one per purchase,
   never batched.

## Project layout

| File | Responsibility | Pattern |
|---|---|---|
| `models.py` | Domain entities, per-office policy (currency, budget, FX) | Rich domain model |
| `adapters.py` | `ChatClient` / `HRClient` interfaces + simulated in-memory fakes | Ports & Adapters |
| `policies.py` | Budget and volunteer-selection strategies | Strategy |
| `service.py` | The refill state machine, orchestrating ports and strategies | Domain service |
| `report.py` | Monthly per-office totals + combined NOK report | — |
| `test_snacks.py` | The 7 tests + tiny runner | — |

## Extensibility

- **New office**: add one `OfficePolicy` entry; nothing else changes.
- **Different rotation** (round-robin, claim-by-reaction): new
  `RotationPolicy` implementation, injected.
- **Stricter budget rule**: new `BudgetPolicy` implementation.
- **Real Slack / real HR API**: implement the two interfaces; `SnackService`
  is untouched and all lifecycle tests keep running against the fakes.

## Test coverage

1. Only one active commitment per refill (double-buy structurally impossible)
2. Expired commitment reassigned to a different volunteer
3. Budget check fires before purchase and blocks approval
4. Manager override path still submits the claim
5. Over-estimate receipt: claim carries the actual amount, flagged for HR
6. Cross-currency monthly totals: per office + combined in NOK
7. Fairness rotation: least-recent volunteer picked, holidays skipped

## Deliberately not built

Receipt OCR, snack-level inventory, a web dashboard, multi-currency wallets,
and a repository layer over in-memory lists. Reasons are in the design
document.
