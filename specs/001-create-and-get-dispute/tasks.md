---

description: "Task list for Create and Get Dispute"
---

# Tasks: Create and Get Dispute

**Input**: Design documents from `/specs/001-create-and-get-dispute/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/disputes.openapi.yaml

**Tests**: REQUIRED. Constitution principle I (NON-NEGOTIABLE): in every phase, write the test
first, run it, and confirm it fails for the expected reason (red) before writing the code that
makes it pass (green). Do not combine a test task and its implementation task into one step.

**Organization**: Tasks are grouped by user story. Stories are P1 (US1, US2) and P2 (US3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 = open a dispute, US2 = reject invalid disputes, US3 = look up a dispute
- All paths are relative to the repository root. Commands: `uv run pytest`, `uv run ruff check .`
- Per CLAUDE.md, the project owner writes the core logic and must be able to explain every
  generated line before committing.

## Phase 1: Setup

**Purpose**: Confirm the baseline before changing anything

- [x] T001 Run `uv sync`, `uv run pytest` and `uv run ruff check .` on branch
  `feat/001-create-and-get-dispute`; confirm the existing `tests/test_health.py` passes and lint
  is clean (no files changed)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `Dispute` model, the repository and the single error format that every story
uses

**CRITICAL**: No user story work can begin until this phase is complete

### Tests first (must fail before T006 to T008)

- [x] T002 [P] Write `tests/test_models.py` (happy path only for now): `DisputeCreate` builds from
  valid data (`txn_0001`, `cust_0001`, amount `"125.50"`, currency `USD`, reason
  `duplicate_charge`); a `Dispute` built from a `DisputeCreate` plus an id and a creation time has
  `state == DisputeState.OPEN`
- [x] T003 [P] Write `tests/test_repository.py`: `InMemoryDisputeRepository.add` then `get` returns
  the same dispute; `get` with an unknown UUID returns `None`; two repository instances do not
  share data
- [x] T004 [P] Write `tests/test_error_format.py`: build a small FastAPI app in the test that
  installs the handlers from `disputes.errors`; assert a request validation failure returns HTTP
  422 with body `{"error": {"code": "validation_error", "message": <str>, "details": [{"field":
  <str>, "message": <str>}]}}`; assert raising `DisputeNotFoundError` returns HTTP 404 with
  `{"error": {"code": "not_found", "message": <str>, "details": []}}`; assert the field name drops
  the leading `body` or `path` location part (for example `amount`, not `body.amount`); assert a
  malformed JSON body gives `field == "body"` (research.md section 7)

### Implementation

- [x] T005 Run `uv run pytest` and record that T002, T003 and T004 fail (import errors); this is
  the red step
- [x] T006 Create `src/disputes/models.py` with `Reason` (str enum: `duplicate_charge`,
  `unrecognized_charge`, `product_not_received`, `incorrect_amount`, `devolution`),
  `DisputeState` (str enum: `open`), `DisputeCreate` (fields `transaction_id: str`, `customer_id:
  str`, `amount: Decimal`, `currency: str`, `reason: Reason`, `description: str | None = None`;
  no constraints yet, they come in US2) and `Dispute` (all `DisputeCreate` fields plus `id: UUID`,
  `state: DisputeState = DisputeState.OPEN`, `created_at: datetime`) (makes T002 pass; the enum
  member names are the upper-case versions of the values, for example `Reason.DUPLICATE_CHARGE`)
- [x] T007 Create `src/disputes/repository.py`: `DisputeRepository` protocol with
  `add(dispute) -> None` and `get(dispute_id: UUID) -> Dispute | None`, and
  `InMemoryDisputeRepository` backed by a dict keyed by id and exposed as the public attribute
  `disputes` so tests can assert that nothing was stored (makes T003 pass; needs T006)
- [x] T008 Create `src/disputes/errors.py`: `DisputeNotFoundError` exception, the error envelope
  Pydantic models (`ErrorDetail`, `ErrorBody`, `ErrorResponse`), and `register_error_handlers(app)`
  that handles `RequestValidationError` (422, `validation_error`) and `DisputeNotFoundError`
  (404, `not_found`) per research.md section 7, including `field == "body"` when no field name
  remains after dropping `body` or `path` (makes T004 pass)
- [x] T009 Run `uv run pytest` and `uv run ruff check .`; T002, T003 and T004 pass (green), lint
  clean

**Checkpoint**: Model, repository and error envelope work; user stories can begin

---

## Phase 3: User Story 1 - Open a dispute (Priority: P1) MVP

**Goal**: `POST /disputes` creates a dispute with a unique id, state `open` and a creation time.

**Independent Test**: Post a valid dispute and check status 201, a `Location` header, a UUID
`id`, the submitted data echoed back, `state` equal to `open`, and `created_at` present.

### Tests first (must fail before T012 and T013)

- [x] T010 [US1] Write `tests/test_create_dispute.py` with these cases, using synthetic data
  (`txn_0001`, `cust_0001`) and a fresh repository per test via
  `app.dependency_overrides`: (a) valid request returns 201, body has all submitted fields, a
  UUID4 `id`, `state == "open"`, a timezone-aware `created_at`, and `amount` serialized as a
  string; (b) `Location` header equals `/disputes/{id}`; (c) request without `description` is
  accepted and the response has `description` null; (d) request with a 1000-character
  `description` is accepted; (e) two requests with the same payload (same transaction) both
  return 201 with different ids; (f) one request per reason value (`duplicate_charge`,
  `unrecognized_charge`, `product_not_received`, `incorrect_amount`, `devolution`) is accepted

### Implementation

- [x] T011 [US1] Run `uv run pytest`; confirm T010 fails (red)
- [x] T012 [US1] Create `src/disputes/routes.py`: an `APIRouter`, a `get_repository` dependency
  returning one app-lifetime `InMemoryDisputeRepository`, and `POST /disputes` that builds a
  `Dispute` with `id=uuid4()`, `state=DisputeState.OPEN`, `created_at=datetime.now(UTC)`, stores
  it, returns it with status 201 and a `Location: /disputes/{id}` header
- [x] T013 [US1] Edit `src/disputes/main.py`: include the router from `routes.py` and call
  `register_error_handlers(app)`; keep `/health` unchanged
- [x] T014 [US1] Run `uv run pytest` and `uv run ruff check .`; T010 passes (green), T002 to T004
  and `tests/test_health.py` still pass, lint clean

**Checkpoint**: User Story 1 works on its own. MVP.

---

## Phase 4: User Story 2 - Reject invalid disputes (Priority: P1)

**Goal**: Invalid input is rejected with HTTP 422 in the standard error format, naming the field,
and creates nothing.

**Independent Test**: Send one invalid field at a time; each response is 422 with a `details`
entry for that field, and a later check of the repository shows no dispute was stored.

### Tests first (must fail before T018 to T019)

- [x] T015 [P] [US2] Extend `tests/test_models.py` with failing-validation cases on
  `DisputeCreate`: `amount` of `0`, `-1`, `"10.001"` and a 13-digit amount such as
  `"12345678901.23"` fail; `amount` `"0.01"`, `"10.50"` and a 12-digit amount such as
  `"1234567890.12"` pass; `reason` `"refund"` and `"Duplicate Charge"` fail; `currency` `"usd"`,
  `"US"`, `"USDX"` and `""` fail, `"USD"` passes; `transaction_id` and `customer_id` of `""`, `"   "` and 65
  characters fail, 1 and 64 characters pass, surrounding whitespace is stripped; `description` of
  1000 characters passes and 1001 characters fails; an unknown field such as `state` fails
- [x] T016 [P] [US2] Extend `tests/test_create_dispute.py` with API cases, each asserting status
  422, `error.code == "validation_error"`, a `details` entry whose `field` is the offending field,
  and that `repository.disputes` is still empty afterwards: amount `0`; amount `-5`; reason not in the
  list; each of `transaction_id`, `customer_id`, `amount`, `currency`, `reason` missing; blank
  `transaction_id`; `description` of 1001 characters; body containing `"state": "closed"`;
  malformed JSON body

### Implementation

- [x] T017 [US2] Run `uv run pytest`; confirm the constraint cases in T015 and T016 fail (red:
  amount, reason, currency, blank or too-long ids, description length, unknown field). Record
  which cases already pass and why (for example a missing required field or malformed JSON is
  already rejected by default); those only guard against regressions
- [x] T018 [US2] Edit `src/disputes/models.py`: add constraints to `DisputeCreate` quoted from
  data-model.md: `transaction_id` and `customer_id` required, stripped, length 1 to 64;
  `amount` required, greater than 0, at most 2 decimal places, at most 12 digits in total;
  `currency` required, matches `^[A-Z]{3}$`; `reason` required, one of the `Reason` values;
  `description` optional, at most 1000 characters; model config forbids unknown fields
  (`extra="forbid"`)
- [x] T019 [US2] Run the T016 cases for malformed JSON and a missing field against the handler
  from T008; if either response is not the standard envelope or its `field` is wrong (a missing
  field must be named, for example `amount`; malformed JSON must give `"body"`), fix
  `src/disputes/errors.py`, otherwise record that no change was needed
- [x] T020 [US2] Run `uv run pytest` and `uv run ruff check .`; T015 and T016 pass (green), all
  earlier tests still pass, lint clean

**Checkpoint**: User Stories 1 and 2 both work

---

## Phase 5: User Story 3 - Look up a dispute (Priority: P2)

**Goal**: `GET /disputes/{dispute_id}` returns the stored dispute, or the standard 404 or 422.

**Independent Test**: Open a dispute through the API, fetch it by id and compare; fetch a random
UUID and get 404; fetch `not-a-uuid` and get 422.

### Tests first (must fail before T023)

- [x] T021 [P] [US3] Write `tests/test_get_dispute.py` with a fresh repository per test:
  (a) create via `POST /disputes`, then `GET /disputes/{id}` returns 200 and a body equal to the
  create response; (b) a well-formed UUID with no dispute returns 404 with `error.code ==
  "not_found"` and `details == []`; (c) `GET /disputes/not-a-uuid` returns 422 with
  `error.code == "validation_error"` and a `details` entry whose `field` is `dispute_id`; (d) a
  fetched dispute still has `state == "open"` and no endpoint other than `POST /disputes` and
  `GET /disputes/{dispute_id}` exists for disputes (`PUT`, `PATCH` and `DELETE` on
  `/disputes/{id}` return 405), covering FR-013

### Implementation

- [x] T022 [US3] Run `uv run pytest`; confirm T021 fails (red)
- [x] T023 [US3] Edit `src/disputes/routes.py`: add `GET /disputes/{dispute_id}` with
  `dispute_id: UUID`; return the dispute from the repository, or raise `DisputeNotFoundError` when
  `get` returns `None`
- [x] T024 [US3] Run `uv run pytest` and `uv run ruff check .`; T021 passes (green), everything
  else still passes, lint clean

### Added after analysis: one error format for framework errors too (constitution IV, FR-012)

- [x] T030 [US3] Write failing tests in `tests/test_error_format.py`: an unknown route returns 404
  with code `not_found`, and `PUT /items/1` on a GET-only route returns 405 with code
  `method_not_allowed`, both in the standard envelope with `details == []`; the `Allow` header
  of the 405 is kept
- [x] T031 [US3] Add `http_error_handler` to `src/disputes/errors.py` for Starlette HTTP errors
  (404 `not_found`, 405 `method_not_allowed`, others `http_error`), keep the exception headers,
  and register it in `register_error_handlers`; update the contract, research.md section 7 and
  data-model.md; tighten T021(d) to assert the 405 error code

**Checkpoint**: All three user stories work

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T025 [P] Compare `/openapi.json` from the running app with
  `specs/001-create-and-get-dispute/contracts/disputes.openapi.yaml` (paths, status codes, field
  rules); fix whichever is wrong. Result: the generated schema documented FastAPI's default
  422 body, no 404 on GET, no `Location` header and an optional `state`; fixed in code with tests
  in `tests/test_openapi.py` (responses declared on both routes, `json_schema_serialization_defaults_required`
  on `Dispute`). Known difference left on purpose: `amount` also accepts a JSON number
- [x] T026 [P] Update `README.md`: document the two endpoints and state that storage is in memory
  and disputes are lost on restart; do not claim persistence (constitution principle VI)
- [x] T027 Walk through every command in `specs/001-create-and-get-dispute/quickstart.md` against
  a running server (`uv run uvicorn disputes.main:app --reload`) and confirm the expected
  statuses and bodies
  Verified 2026-11-12 against a real server: create 201 with `Location`, fetch 200 with the same
  data, unknown id 404, `amount` 0 and caller-set `state` 422, `PUT` 405 with `Allow: GET`, all in
  the standard envelope; after a restart the old id returns 404 (in-memory storage)
- [x] T028 Final run of `uv run pytest` and `uv run ruff check .`; confirm all tests pass and
  lint is clean, and confirm no real data or secrets are in any new file (principle III)
  Verified 2026-11-12: 76 tests pass, ruff clean; a scan of changed and new files for keys,
  tokens and emails found only the text of this task; the only ids used are `txn_0001` and
  `cust_0001`; `.env` exists locally but is git-ignored and not tracked
- [ ] T029 Before committing, the owner reads every changed file and can explain each line
  (CLAUDE.md rule); then open a PR from `feat/001-create-and-get-dispute` into `develop` and
  confirm CI is green on the PR before merging (constitution, Development Workflow)

---

## Dependencies & Execution Order

- Phase 1 first, then Phase 2 (blocks everything), then US1, US2, US3, then Phase 6.
- US1 needs Phase 2. US2 builds on US1 (it adds constraints to the model created in T006). US3
  needs Phase 2 and the `POST` route from US1 to create test data through the API.
- In Phase 2, T007 (repository) needs the models from T006, so do T006 first.
- Within each phase: tests, then the red run, then implementation, then the green run.

## Parallel Opportunities

- T002, T003 and T004 (different test files)
- T015 and T016 (different test files)
- T025 and T026 (different files)

## Implementation Strategy

- **MVP**: Phase 1, Phase 2 and US1 (T001 to T014): a customer can open a dispute and get it
  back with state `open`.
- **Increment 2**: US2 (validation and errors), then US3 (lookup).
- Commit after each green checkpoint, with a conventional message, and only after the owner can
  explain the code.
