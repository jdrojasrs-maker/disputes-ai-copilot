# Implementation Plan: Dispute Intake from Free Text

**Branch**: `docs/spec-kit-005-disputes-intake` (spec and plan); the code branch is not yet created | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-disputes-intake/spec.md`

## Summary

Add `POST /disputes/intake`. One free-text message goes in; the service makes **one** call to the
existing `LLMClient`, asks for a JSON object with the dispute fields (absent fields as `null`),
and treats the answer as untrusted. The code, not the model, then runs a fixed sequence of
checks: the answer is valid JSON of the expected shape, every identifier and the amount
literally appear in the message, the message names a single transaction, no required field is
missing, and the transaction exists for that customer (through a new async `TransactionLookup`
Protocol with a synthetic in-package implementation). Only then is the dispute created, with the
same code path as `POST /disputes` and the original message as its description.

Each failure kind has its own error code in the API's single error format. No new third-party
dependency. The provider is chosen by one new setting (`LLM_PROVIDER`) read when the client is
first needed. Tests use the existing `FakeLLMClient`; nothing in the 001-004 tests is modified.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, Pydantic v2 (existing). Standard library only for the rest (`json`, `re`, `decimal`). **No new dependency.**

**Storage**: The existing in-memory dispute repository (unchanged). The sample transactions are a module-level constant, read-only.

**Testing**: pytest with the existing `client` fixture and `FakeLLMClient`; the autouse network guard stays on. The endpoint is `async def` (the client is async), which `TestClient` already supports.

**Target Platform**: Linux container (CI) and Windows dev machine

**Project Type**: Single Python web-service project

**Performance Goals**: None. Latency and cost per case are measured by the evals feature (E5), not here (spec SC-006).

**Constraints**: Exactly one model call per request; no retries; no message text, model output, key or provider message in any error body or log; no real model or network in tests; one process (in-memory store, as today).

**Scale/Scope**: Two new source modules (`intake.py`, `transactions.py`), one small factory in `llm/`, one new route and its error handlers, one new `.env.example` variable, about 10 test functions.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Tests first, focused | Pass | About 10 test functions (see "Test plan"), red then green, each explainable line by line. Under the ~15 limit, so no extra justification. |
| II. Valid state transitions | Pass | Intake only creates disputes in `open` through the existing creation path; it adds no transition. |
| III. Synthetic data only | Pass | Sample transactions and every test message are synthetic. The service never logs the message. Real PII sent to a provider is out of scope until feature 012 (declared in the spec). |
| IV. Validate at the boundary | Pass | The request body is a Pydantic model; the model's answer is validated by Pydantic before it reaches domain code; every error uses the existing single format, covered by tests. |
| V. Independent service | Pass | Bank is neither called nor modified; the lookup is an interface with a simulated implementation. |
| VI. Honest documentation | Pass | The README and `CLAUDE.md` will claim only what the tests prove; extraction accuracy is stated as not measured until E5. Unverified facts are labeled in `research.md`. |
| Technical Constraints: new core dependency | Pass | None added. |

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-disputes-intake/
├── plan.md              # This file
├── research.md          # Phase 0: decisions, alternatives, what is not verified
├── data-model.md        # Phase 1: the new types and the order of checks
├── quickstart.md        # Phase 1: how to prove it works
├── contracts/
│   └── intake-contract.md   # Phase 1: request, responses, error table
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks) - not created here
```

### Source Code (repository root)

```text
src/disputes/
├── intake.py            # NEW: request/extraction models, prompt, parsing, the checks, intake errors
├── transactions.py      # NEW: TransactionLookup Protocol + SampleTransactionLookup (synthetic data)
├── routes.py            # CHANGED: POST /disputes/intake, two dependencies, new_dispute() helper
├── errors.py            # CHANGED: handlers for the intake errors and for LLMError
├── models.py            # unchanged
├── repository.py        # unchanged
└── llm/
    └── factory.py       # NEW: build_llm_client() chooses the adapter from LLM_PROVIDER

tests/
├── test_intake.py       # NEW: the endpoint behavior (about 8 functions)
├── test_intake_checks.py# NEW: pure checks: amount matching, identifier matching (about 2 functions)
└── (existing tests are not modified)

.env.example             # CHANGED: LLM_PROVIDER placeholder
```

**Structure Decision**: Single project, flat modules, like the existing code. The checks live in
`intake.py` as plain functions with no I/O so they are testable without the HTTP layer. The
route stays thin: call the model, call the checks, call the lookup, create. `create_dispute`
is refactored only to extract `new_dispute(data)` (build the record with id, state and
timestamps) so both routes build disputes the same way; its behavior and its tests do not
change.

## Design

### Order of work in the route (this order is the contract)

1. **Validate the body** (`IntakeRequest`): non-blank, at most 1000 characters, unknown fields
   rejected. Failure: the existing `validation_error` (422). The model is not called.
2. **Call the model once** with the system prompt and the message. A provider failure
   (`LLMError`) is mapped to its own error (table in the contract). Nothing else runs.
3. **Parse and validate the answer**: it must be a JSON object that fits `ExtractedDispute`,
   and the model must have stopped normally. Otherwise: `unreliable_model_answer`.
4. **Verify against the text**: each `transaction_ids` entry, `customer_id` and `amount`, when
   present, must literally appear in the message (rules in `research.md`). Otherwise:
   `unreliable_model_answer`.
5. **Ambiguity**: more than one transaction id: `ambiguous_message`.
6. **Missing fields**: any of the five required fields absent: `missing_fields` listing all of
   them.
7. **Build `DisputeCreate`** from the extracted values. If the existing validation rejects them
   (for example an amount with three decimals), that is also `unreliable_model_answer`: the
   service does not repair values.
8. **Look up the transaction** for that customer. Not found or not theirs, same response:
   `transaction_not_found`.
9. **Create** with the same helper as `POST /disputes`, description = the original message.
   Respond 201 with `Location`.

Unreliable checks run before ambiguity and missing fields on purpose: once the model has been
caught inventing, none of its output is trusted, so it is not used to tell the caller what is
missing.

### Provider selection

A new variable `LLM_PROVIDER` (`anthropic` or `azure_openai`, no default) is read by
`build_llm_client()` in `llm/factory.py`, which calls the existing `from_env()` of the chosen
adapter. The route gets the client through a FastAPI dependency (`get_llm_client`) that builds it
once per process on first use (so importing the app never needs a key, as with the adapters) and
that tests override with `FakeLLMClient`. A missing or unknown `LLM_PROVIDER`, or a missing
adapter setting, raises the existing `LLMConfigurationError`; the route returns a generic 500
`llm_not_configured` without naming settings.

### Async route and the lock

The route is `async def` because `LLMClient.complete` is async. The repository's `add` takes a
`threading.Lock` for microseconds with no I/O inside, so calling it from the event loop is
acceptable. The in-memory store and its lock remain per process (known limit, unchanged).

### Test plan (about 10 functions; owner explains each line)

Written first, red then green. All use the real app and `FakeLLMClient`.

| # | Test | Covers |
|---|---|---|
| 1 | A complete message creates an `open` dispute with the extracted values, description equal to the message, and it can be fetched | US1, FR-001, FR-011 |
| 2 | Missing fields: the error lists exactly the absent ones, nothing is created | US2, FR-004, FR-005 |
| 3 | A value not in the text (id, customer, amount: parametrized) is `unreliable_model_answer`, not `missing_fields`, nothing created | US4, FR-006 |
| 4 | Not valid JSON, and a reason outside the allowed values (parametrized): `unreliable_model_answer` | FR-007 |
| 5 | Two transactions named: `ambiguous_message`, nothing created | FR-017 |
| 6 | Unknown transaction and another customer's transaction give identical responses; nothing created | US3, FR-008, FR-010 |
| 7 | Each `LLMError` kind (parametrized over the six) gives its own code and the planned status; no secret in the body | US5, FR-012 |
| 8 | Empty and over-long messages are rejected and the fake records zero model calls | FR-015, FR-013 |
| 9 | Amount matching rules (`45.000`, `45,000`, `$45000`, `1.234,56`, `12.50`) accept the right value and reject the wrong one | research.md, amount rule |
| 10 | Identifier matching respects boundaries (`T-7` is not found inside `T-789`) | research.md, identifier rule |

Low-risk edge cases not tested, kept as a list in `research.md`: extra fields ignored, currency
bare symbol, blank-but-valid JSON types, the provider factory's error text.

## Post-Design Constitution Re-check

Re-read after writing `research.md`, `data-model.md` and the contract: no principle changes
status. The only new risk, the model being the first untrusted input, is the subject of steps
3-4 above and tests 3-4. No dependency was added.
