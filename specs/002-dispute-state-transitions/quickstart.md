# Quickstart: Dispute State Transitions

How to confirm the feature works once implemented. All data is synthetic.

## Prerequisites

- Python 3.12 and uv installed
- Dependencies installed: `uv sync`

## 1. Automated checks

```bash
uv run pytest
uv run ruff check .
```

Expected: all tests pass and lint is clean. Per principle I, each test must have been seen
failing before its code was written.

To run only the concurrency tests (they repeat each race at least 50 times):

```bash
uv run pytest tests/test_transition_concurrency.py tests/test_repository.py -v
```

Expected: every round passes. If the lock in the repository is removed, the repository test
`test_transition_is_atomic_under_a_slow_read` fails; that is the proof that the lock is needed.

## 2. Manual check against a running server

Start the server:

```bash
uv run uvicorn disputes.main:app --reload
```

Open a dispute and keep its `id` (expect `201`, `state` `open`, `updated_at` equal to
`created_at`, `history` empty):

```bash
curl -i -X POST http://127.0.0.1:8000/disputes \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"txn_0001","customer_id":"cust_0001","amount":"125.50",
       "currency":"USD","reason":"refund_not_received"}'
```

Take it under review (expect `200`, `state` `under_review`, one history entry from `open`):

```bash
curl -i -X POST http://127.0.0.1:8000/disputes/<id>/transitions \
  -H "Content-Type: application/json" \
  -d '{"to_state":"under_review","note":"Documents received"}'
```

Skip a step is refused (expect `409`, `error.code` = `invalid_transition`; fetch the dispute and
confirm nothing changed). Use a fresh `open` dispute:

```bash
curl -i -X POST http://127.0.0.1:8000/disputes/<id-of-an-open-dispute>/transitions \
  -H "Content-Type: application/json" \
  -d '{"to_state":"resolved"}'
```

Close it, then try to reopen it (expect `200`, then `409`):

```bash
curl -i -X POST http://127.0.0.1:8000/disputes/<id>/transitions \
  -H "Content-Type: application/json" -d '{"to_state":"resolved"}'
curl -i -X POST http://127.0.0.1:8000/disputes/<id>/transitions \
  -H "Content-Type: application/json" -d '{"to_state":"open"}'
```

Read the history (expect two entries in order, and `updated_at` equal to the last `changed_at`):

```bash
curl -i http://127.0.0.1:8000/disputes/<id>
```

Invalid inputs (expect `422` each): unknown state `{"to_state":"closed"}`, missing state `{}`,
extra field `{"to_state":"resolved","from_state":"open"}`. Unknown dispute id (expect `404`):

```bash
curl -i -X POST http://127.0.0.1:8000/disputes/00000000-0000-4000-8000-000000000000/transitions \
  -H "Content-Type: application/json" -d '{"to_state":"under_review"}'
```

Old reason (expect `422` naming `reason`): create a dispute with `"reason":"devolution"`.

## Notes

- Storage is in memory: restarting the server loses all disputes and histories.
- Atomic transitions hold inside one process. With several worker processes each has its own
  memory and lock; PostgreSQL (a later feature) removes that limit.
- Request and response shapes: [contracts/disputes.openapi.yaml](contracts/disputes.openapi.yaml).
- Field rules and the transition table: [data-model.md](data-model.md).
