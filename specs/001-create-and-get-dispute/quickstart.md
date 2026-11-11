# Quickstart: Create and Get Dispute

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

## 2. Manual check against a running server

Start the server:

```bash
uv run uvicorn disputes.main:app --reload
```

Open a dispute (expect `201`, state `open`, a new `id`, and a `Location` header):

```bash
curl -i -X POST http://127.0.0.1:8000/disputes \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"txn_0001","customer_id":"cust_0001","amount":"125.50",
       "currency":"USD","reason":"duplicate_charge"}'
```

Fetch it with the returned id (expect `200` and the same data):

```bash
curl -i http://127.0.0.1:8000/disputes/<id-from-previous-response>
```

Unknown id (expect `404`, `error.code` = `not_found`):

```bash
curl -i http://127.0.0.1:8000/disputes/00000000-0000-4000-8000-000000000000
```

Invalid amount (expect `422`, `error.code` = `validation_error`, a detail with field `amount`):

```bash
curl -i -X POST http://127.0.0.1:8000/disputes \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"txn_0001","customer_id":"cust_0001","amount":"0",
       "currency":"USD","reason":"duplicate_charge"}'
```

Caller-chosen state (expect `422`):

```bash
curl -i -X POST http://127.0.0.1:8000/disputes \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"txn_0001","customer_id":"cust_0001","amount":"10.00",
       "currency":"USD","reason":"devolution","state":"closed"}'
```

## Notes

- Storage is in memory: restarting the server loses all disputes. This is expected until the
  PostgreSQL feature.
- Request and response shapes: [contracts/disputes.openapi.yaml](contracts/disputes.openapi.yaml).
- Field rules: [data-model.md](data-model.md).
