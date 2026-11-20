# Data Model: Dispute Intake from Free Text

No stored data changes. `Dispute`, `DisputeCreate` and the repository are untouched. These are
the new in-memory types.

## IntakeRequest (the body)

| Field | Rule |
|---|---|
| `message` | String. Not blank (whitespace-only is rejected). 1 to 1000 characters, the same maximum as `Dispute.description` so the original text always fits. |

Unknown fields are rejected (`extra="forbid"`, like `DisputeCreate`). The text is kept exactly as
sent; it is not trimmed, because it becomes the dispute's description (FR-011).

## ExtractedDispute (the model's answer, after parsing)

Every field is optional: absent means the text does not state it.

| Field | Type | Meaning |
|---|---|---|
| `transaction_ids` | list of strings, default empty | Every transaction id the text names. Empty: none. More than one: ambiguous. |
| `customer_id` | string or null | The customer id the text states. |
| `amount` | decimal or null | The amount the text states, as a number. |
| `currency` | string or null | Three-letter code, only if the text makes it clear. |
| `reason` | one of the five `Reason` values, or null | The model's classification. A value outside the five is a parse failure. |

Unknown fields in the answer are ignored. This type is never stored or returned; it exists only
between the model call and the checks.

## TransactionLookup (Protocol)

```text
async exists_for_customer(transaction_id: str, customer_id: str) -> bool
```

True only if the transaction exists and belongs to that customer. One boolean on purpose: "does
not exist" and "belongs to someone else" cannot be told apart by the route.

`SampleTransactionLookup` holds a small read-only mapping `transaction_id -> customer_id` of
synthetic values (a handful of entries, all invented). It lives in the package because the
service needs it at run time.

## Intake errors (domain exceptions in `intake.py`)

| Exception | Raised when | Maps to code |
|---|---|---|
| `UnreliableModelAnswerError` | steps 3, 4 and 7 of the order of work | `unreliable_model_answer` |
| `AmbiguousMessageError` | more than one transaction id | `ambiguous_message` |
| `MissingFieldsError(fields)` | a required field is absent; carries the field names | `missing_fields` |
| `TransactionNotFoundError` | the lookup returned false | `transaction_not_found` |

Provider failures are not wrapped: the route lets `LLMError` and its subclasses propagate to a
handler that maps them (contract table). `LLMConfigurationError` is mapped separately.

## Order of checks

```text
body valid? -> model call -> answer parses? -> values in text? -> one transaction?
   -> nothing missing? -> DisputeCreate valid? -> transaction is the customer's? -> create
```

The first failing step decides the response; later steps do not run. Nothing is stored before
the last step.
