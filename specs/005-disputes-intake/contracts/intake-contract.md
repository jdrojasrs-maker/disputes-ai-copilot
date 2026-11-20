# Contract: POST /disputes/intake

## Request

`POST /disputes/intake`, `Content-Type: application/json`

```json
{ "message": "I was charged twice for transaction TX-1001. I am customer C-100. The amount was 45.000 COP and the second charge was a duplicate." }
```

| Field | Type | Rule |
|---|---|---|
| `message` | string | Required. Not blank. At most 1000 characters. No other fields. |

(All values in examples are synthetic.)

## Success

`201 Created`, header `Location: /disputes/{id}`, body identical in shape to the body of
`POST /disputes`:

```json
{
  "transaction_id": "TX-1001",
  "customer_id": "C-100",
  "amount": "45000.00",
  "currency": "COP",
  "reason": "duplicate_charge",
  "description": "I was charged twice for transaction TX-1001. I am customer C-100. ...",
  "id": "…",
  "state": "open",
  "created_at": "…",
  "updated_at": "…",
  "history": []
}
```

`description` is the original message, unchanged.

## Errors

All errors use the API's single format:

```json
{ "error": { "code": "…", "message": "…", "details": [ { "field": "…", "message": "…" } ] } }
```

| Status | `code` | When | `details` |
|---|---|---|---|
| 422 | `validation_error` | Body invalid: blank, over 1000 characters, unknown field | the existing field list |
| 422 | `missing_fields` | The text does not state one or more required fields | one entry per absent field: `field` is `transaction_id`, `customer_id`, `amount`, `currency` or `reason` |
| 422 | `ambiguous_message` | The text names more than one transaction | empty |
| 422 | `transaction_not_found` | The transaction does not exist or is not that customer's (same response for both) | empty |
| 502 | `unreliable_model_answer` | The model's answer is unusable or states something the text does not | empty |
| 502 | `llm_authentication_error` | The provider rejected the service's credentials | empty |
| 502 | `llm_bad_request` | The provider rejected the request | empty |
| 502 | `llm_error` | Any other non-retryable provider failure | empty |
| 503 | `llm_rate_limited` | Provider rate limit. Retryable | empty |
| 503 | `llm_unavailable` | Provider unavailable. Retryable | empty |
| 504 | `llm_timeout` | Provider timed out. Retryable | empty |
| 500 | `llm_not_configured` | The service has no usable model settings | empty |

Rules for every error:

- Nothing is created.
- `message` is fixed text written by the service. It never contains the caller's message, the
  model's output, a key, or the provider's own error text.
- `transaction_not_found` gives the same body whether the transaction is unknown or belongs to
  another customer.
- `unreliable_model_answer` never says which value failed or why.
- Retrying is safe only for 503 and 504. The service itself makes one model call and never
  retries.

## Not part of the contract

Successful intake is not idempotent: the same message twice creates two disputes. There is no
authentication. `POST /disputes` is unchanged and still accepts any transaction id.
