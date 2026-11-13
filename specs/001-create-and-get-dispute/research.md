# Research: Create and Get Dispute

No `NEEDS CLARIFICATION` items remained in the Technical Context. The items below are the
decisions the spec deferred to planning.

## 1. Storage

- **Decision**: In-memory repository behind a `DisputeRepository` protocol.
- **Rationale**: The constitution says PostgreSQL, SQLAlchemy and Alembic arrive in a later
  feature. Adding them now would widen this feature beyond one deliverable. The protocol lets the
  later feature swap the implementation without changing routes or tests.
- **Alternatives considered**: Add Postgres now (rejected: out of scope, needs migrations and
  Docker in CI); JSON file (rejected: throwaway code with no path to the real store).
- **Consequence**: The spec assumption "disputes survive a restart" is moved to the Postgres
  feature. The spec was updated to say so (VI: do not claim what does not exist).

## 2. Identifiers

- **Decision**: Dispute id is a server-generated UUID4, exposed as a string.
- **Rationale**: Not guessable or sequential, needs no database. An id with a bad format on GET
  is a validation error handled by the same error envelope.
- **Alternatives considered**: Sequential integers (rejected: guessable); ULID (rejected: extra
  dependency).

## 3. Money and currency

- **Decision**: Amount is `Decimal`, greater than zero, at most two decimal places and at most
  12 digits in total (the 12 is a defensive bound chosen here, not from the spec). Currency is
  a string matching three uppercase letters (`^[A-Z]{3}$`). The list of real ISO 4217 codes is
  not enforced.
- **Rationale**: Floats lose precision for money. Format-only currency validation satisfies the
  spec without embedding a currency table to maintain.
- **Alternatives considered**: Integer minor units (rejected: currencies differ in exponent, and
  the spec talks about amounts, not minor units); full ISO list (deferred).
- **Serialization**: Amount is returned as a string (for example `"125.50"`) so clients do not
  lose precision. Pydantic v2 serializes `Decimal` as a string in JSON mode.

## 4. Reason and state values

- **Decision**: Reason is a `str` enum with values `duplicate_charge`, `unrecognized_charge`,
  `product_not_received`, `incorrect_amount`, `devolution`. State is a `str` enum with the single
  value `open`.
- **Rationale**: Stable snake_case wire values; the enum makes invalid values fail validation.
- **Alternatives considered**: Accept human text such as "duplicate charge" (rejected: spacing
  and case ambiguity, flagged in the spec edge cases).

## 5. State chosen by the caller

- **Decision**: Request models forbid unknown fields (`extra="forbid"`), so a request that sends
  `state` is rejected with a validation error.
- **Rationale**: FR-007 requires rejecting. Rejecting is explicit and testable, and
  avoids silently dropping data.
- **Alternatives considered**: Silently ignore extra fields (rejected: hides client mistakes).

## 6. Identifier text fields

- **Decision**: `transaction_id` and `customer_id` are strings, whitespace stripped, length 1 to
  64.
- **Rationale**: Opaque ids from other systems (spec assumption). Stripping makes a
  whitespace-only value count as blank (FR-004). The 64 limit is a defensive bound, not from the
  spec; it is recorded here so it can be challenged.

## 7. Error format

- **Decision**: Every error response has this body:

  ```json
  {"error": {"code": "validation_error", "message": "Request validation failed",
             "details": [{"field": "amount", "message": "Input should be greater than 0"}]}}
  ```

  Codes: `validation_error` (HTTP 422), `not_found` (HTTP 404, both a missing dispute and an
  unknown route), `method_not_allowed` (HTTP 405). Other framework HTTP errors use `http_error`. `details` is empty for
  `not_found`. A custom handler for `RequestValidationError` and a handler for the not-found
  domain exception produce this shape.
- **Rationale**: Constitution IV requires one consistent format. FastAPI's default 422 body
  differs from a hand-made 404 body, so the default must be overridden.
- **Field names**: Taken from the Pydantic error location, dropping the leading `body` or `path`
  part. When nothing remains (the whole body is at fault, for example malformed JSON or a body
  that is not an object), `field` is `"body"`.
- **Alternatives considered**: RFC 9457 problem details (rejected for now: more fields than the
  feature needs; can be adopted in a later amendment).

## 8. Creation time

- **Decision**: `created_at` is a timezone-aware UTC datetime set by the server at creation.
- **Rationale**: FR-008 requires storing creation time; UTC avoids timezone ambiguity.
