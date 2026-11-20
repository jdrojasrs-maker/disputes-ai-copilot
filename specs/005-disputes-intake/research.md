# Research: Dispute Intake from Free Text

Decisions the spec left to the plan. "Not verified" marks anything not checked against
documentation or a real run.

## R1. HTTP status per error

**Decision**: caller-fixable problems are 422; failures of the model are 5xx; retryable and
non-retryable provider failures use different statuses and different codes.

| Situation | Code | Status |
|---|---|---|
| Body invalid (empty, too long, unknown field) | `validation_error` (existing) | 422 |
| Required fields absent | `missing_fields` | 422 |
| Several transactions in the message | `ambiguous_message` | 422 |
| Transaction unknown, or not the customer's | `transaction_not_found` | 422 |
| Model answer unusable or not supported by the text | `unreliable_model_answer` | 502 |
| Provider: bad credentials | `llm_authentication_error` | 502 |
| Provider: rejected the request | `llm_bad_request` | 502 |
| Provider: rate limit (retryable) | `llm_rate_limited` | 503 |
| Provider: unavailable (retryable) | `llm_unavailable` | 503 |
| Provider: timeout (retryable) | `llm_timeout` | 504 |
| Provider: any other `LLMError` (not retryable) | `llm_error` | 502 |
| Provider not configured | `llm_not_configured` | 500 |

**Rationale**: 422 matches the API's existing validation errors, so a client treats "fix your
input" uniformly. 404 is kept for "this URL's resource does not exist" (disputes by id), which is
not the situation for a transaction named in a body. 502 says "an upstream we depend on gave
something unusable"; 503/504 are the statuses clients already retry. `retryable` is the class
attribute of the existing errors, so the handler reads it instead of repeating the list. 429 is
avoided on purpose: it would read as "you called too often" when the limit is the service's
own provider quota.

**Alternatives**: 400 for caller errors (rejected: the API already uses 422). 409 for ambiguity
(rejected: no state conflict). One generic `llm_error` for all provider failures (rejected: the
spec requires distinguishable kinds).

**Not verified**: no `Retry-After` header is sent; the adapters do not expose the provider's
value. Left out rather than guessed.

## R2. Parsing the model's answer: strict, no repair

**Decision**: `json.loads` on the answer text exactly as returned, with `parse_float=Decimal`
so `45000.50` never passes through a binary float. It must be a JSON object. A Markdown code
fence around the JSON, trailing text, or a stop reason of `max_tokens` (cut-off answer) is
`unreliable_model_answer`. The prompt asks for JSON only.

**Rationale**: FR-007 forbids repairing. Stripping fences would be small, but it is the first
step of a slippery rule set ("also accept this, also that") whose cost is measured nowhere.
If real runs show a provider always fences its JSON, that becomes a deliberate change backed by
numbers from E5.

**Not verified**: how often each provider returns bare JSON under this prompt. No real call is
made by this feature; E5 measures it. Expect some false rejections until then.

## R3. Matching identifiers against the text

**Decision**: a `transaction_id` or `customer_id` is accepted only if it appears in the message
as an exact, case-sensitive match that is **not part of a longer token**: the characters on both
sides must not be a letter, digit, `_` or `-`. In regex terms: `(?<![\w-])<id>(?![\w-])`, with
the id escaped.

**Rationale**: a plain substring test would accept `T-7` as "present" inside `T-789`, which is
exactly the invention the check exists to catch. Case-sensitive because the lookup is exact: if
the model changed the case, its value would not equal what the customer wrote.

**Alternatives**: case-insensitive match (rejected: would store a value the text does not
contain). Fuzzy matching (rejected: guesses).

## R4. Matching the amount against the text

**Decision**: find every number-like token in the message (`\d[\d.,]*\d|\d`) and compute the
values it can mean. Rule per token:

- If the last separator (`.` or `,`) is followed by **one or two** digits, it is the decimal
  point; every other separator is a thousands separator and is dropped (`1.234,56` is
  1234.56; `12.50` is 12.5).
- Otherwise every separator is a thousands separator (`45.000` and `45,000` are 45000;
  `1,234` is 1234).
- A leading currency symbol or trailing letters are not part of the token.

The extracted amount is accepted if it equals the value of any token (compared as `Decimal`).

**Rationale**: Colombian texts write `45.000` and US texts write `45,000`; both mean forty-five
thousand. Treating three digits after a separator as thousands avoids accepting `45` for
`45.000`, the most damaging mismatch.

**Not supported (rejected as unreliable, documented limit)**: amounts written in words
(`cuarenta y cinco mil`), abbreviations (`45k`, `45 mil`), ranges. A real message like
`45 mil pesos` will be rejected by this feature; whether to widen the rule is a decision for
after E5 shows how common it is.

## R5. Detecting several transactions

**Decision**: the extraction schema has `transaction_ids`, a list. The prompt asks for **every**
transaction id the message names. More than one entry: `ambiguous_message`. An empty list means
absent.

**Rationale**: ambiguity must be detectable without the service knowing what an id looks like.
A list lets the model report two without forcing it to choose.

**Known limit**: this relies on the model listing all of them. The code cannot find a second id
the model left out. The check on each listed id still stops an invented one. Stated honestly in
the README when the feature closes.

## R6. Currency and reason are not verified against the text

**Decision**: only transaction id, customer id and amount are checked against the text (as the
spec says). `currency` is validated by the existing rule (three capital letters). `reason` must
be one of the five allowed values; the model classifies it, so it cannot be matched literally.
The prompt instructs the model to return `null` for a currency it cannot tell (a bare `$`) and
for a reason that fits none.

**Not verified**: how well the prompt makes models follow the null rule for currency. Extraction
accuracy is measured by E5.

## R7. Where provider selection lives

**Decision**: a new variable `LLM_PROVIDER` read in `llm/factory.py`; the route depends on
`get_llm_client`, built once per process on first use.

**Rationale**: spec FR-014 says the endpoint names no provider. A single place that reads the
variable keeps that true. Lazy build keeps "importing the app needs no key" (a rule the adapters
already follow).

**Alternatives**: infer the provider from which keys are present (rejected: silent and
surprising when both are set). Build at import time (rejected: breaks `/health` and tests
without keys).

## R8. TransactionLookup is async

**Decision**: `async def exists_for_customer(transaction_id, customer_id) -> bool`. The sample
implementation does no I/O.

**Rationale**: the real implementation (Bank, feature 010) is a network call. Making the
Protocol async now means feature 010 swaps the implementation without changing the route.
Returning a single boolean also makes "not found" and "not theirs" the same answer by
construction (FR-010), instead of relying on the route to merge two outcomes.

**Alternatives**: a sync Protocol like the repository (rejected: would force a signature change
later). Returning the transaction record (rejected: intake does not use it; clarification Q3).

## R9. Not logging the message

**Decision**: the service writes no log line containing the message, the extraction or the
model's raw answer. Error bodies carry fixed text only.

**Rationale**: messages are customer text; a log is the easiest place for it to leak. Even
with synthetic data now, the habit is cheaper to start now than to retrofit before feature 012.

## Low-risk edge cases (not tested, recorded)

- Extra fields in the model's JSON are ignored (`extra="ignore"` on `ExtractedDispute`).
- A currency given as a bare symbol is the model's to return as `null`; not tested without a
  real model.
- Message with only whitespace between words is valid input; only fully blank is rejected.
- `amount` returned as a JSON string (`"45000"`) is accepted by Pydantic's normal conversion.
- `LLM_PROVIDER` unset or unknown gives `llm_not_configured`; the exact text is not asserted.
