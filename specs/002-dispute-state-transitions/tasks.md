---

description: "Task list for Dispute State Transitions"
---

# Tasks: Dispute State Transitions

**Input**: Design documents from `/specs/002-dispute-state-transitions/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/disputes.openapi.yaml

**Tests**: REQUIRED. Constitution principle I (NON-NEGOTIABLE): in every phase, write the test
first, run it, and confirm it fails for the expected reason (red) before writing the code that
makes it pass (green). Do not combine a test task and its implementation task into one step. When
a test already passes at its red run, record that and why; it then only guards against regressions.

**Organization**: Tasks are grouped by user story. US1, US2 and US3 are P1, US4 is P2, US5 is P3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 = move a dispute through its lifecycle, US2 = refuse invalid transitions,
  US3 = resolve concurrent transitions safely, US4 = updated_at and history, US5 = renamed reason
- All paths are relative to the repository root. Commands: `uv run pytest`, `uv run ruff check .`
- **Who writes what** (CLAUDE.md): tasks tagged *(owner)* are core logic (models, rules,
  repository, endpoint, errors) that the project owner writes and must be able to explain line by
  line before committing. Tasks tagged *(AI may draft)* are documentation or test scaffolding the
  assistant can generate; the owner still reviews them. Untagged tasks are runs and checks. For
  tests, the owner tries first and the assistant explains and reviews.
- Not in this feature: the Dockerfile and the CI image (separate infrastructure change), and
  PostgreSQL (feature 006).

## Phase 1: Setup

**Purpose**: Confirm the baseline before changing anything

- [X] T001 Confirm you are on branch `feat/002-dispute-state-transitions`, then run `uv sync`,
  `uv run pytest` and `uv run ruff check .`; record the number of passing tests (76 expected) and
  that lint is clean (no files changed)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The five states, the single transition table, the new model fields and the 409
error, which every story uses

**CRITICAL**: No user story work can begin until this phase is complete

### Tests first (must fail before T008 to T011)

- [X] T002 [P] Write `tests/test_transitions.py` for the module `disputes.transitions`
  (data-model.md, "Transition rules"): `is_allowed(from_state, to_state)` is true for exactly
  these 5 pairs: `open→under_review`, `open→withdrawn`, `under_review→resolved`,
  `under_review→rejected`, `under_review→withdrawn`, and false for the other 20 of the 25 pairs
  (parametrize over all `DisputeState` x `DisputeState`, including a state to itself and every
  move back to `open`); `ALLOWED_TRANSITIONS` has a key for each of the 5 states and its value
  for `resolved`, `rejected` and `withdrawn` is an empty set (SC-002, FR-002 to FR-004)
- [X] T003 [P] Extend `tests/test_models.py`: (a) the set of `DisputeState` values is exactly
  `open`, `under_review`, `resolved`, `rejected`, `withdrawn`; (b) `TransitionRequest` accepts
  each of the five values as `to_state`; rejects `"closed"`, `"Resolved"`, `""` and a missing
  `to_state`; rejects an unknown field such as `from_state` or `updated_at`
  (`extra="forbid"`); `note` defaults to `None`; a note of 1000 characters passes and 1001 fails;
  a note of `""` or `"   "` becomes `None`; a note of `"  keep as sent  "` is stored unchanged;
  (c) `StateChange` holds `from_state`, `to_state`, `note` (string or `None`) and a
  timezone-aware `changed_at`; (d) a `Dispute` built with `updated_at` has `history == []` by
  default and a separate list for each instance; a `Dispute` built without `updated_at` raises
  `ValidationError`; (e) update the existing `test_dispute_starts_open` and any other test that
  builds a `Dispute` to pass `updated_at`
- [X] T004 [P] Extend `tests/test_error_format.py`: add a route to the test app that raises
  `InvalidTransitionError(from_state=DisputeState.RESOLVED, to_state=DisputeState.REJECTED)`;
  assert HTTP 409 and body `{"error": {"code": "invalid_transition", "message": <str>,
  "details": []}}`, and that the message contains `resolved` and `rejected`; add a second route
  that raises `InvalidTransitionError(from_state=DisputeState.UNDER_REVIEW,
  to_state=DisputeState.WITHDRAWN, state_changed=True)` and assert HTTP 409, the same code
  `invalid_transition`, `details == []`, a message that contains `changed` and `under_review`, and
  that it does not say the move is not allowed (it must not contain `Cannot change state`),
  because the move may be allowed from the new state (research.md section 4)
- [X] T005 [P] Edit `tests/test_repository.py`: the helper `make_dispute()` passes
  `updated_at=created_at` (same value) so the existing four tests keep their meaning
- [X] T006 [P] Extend `tests/test_create_dispute.py` (FR-011, FR-012; US4 scenario 1): the 201 body
  of `POST /disputes` has `updated_at` equal to `created_at` and `history == []`; the dispute
  stored in the repository (`repository.get(id)`) has the same `updated_at` and an empty `history`
  (this assertion is written before the code that satisfies it, T011)

### Implementation

- [X] T007 Run `uv run pytest` and record that T002, T003, T004, T005 and T006 fail (import
  errors, a missing `updated_at`, a missing `InvalidTransitionError`, `updated_at` and `history`
  absent from the create response); this is the red step. The existing tests that build a
  `Dispute` also fail until T008 to T011 are done
- [X] T008 *(owner)* Edit `src/disputes/models.py`: `DisputeState` gets the values `open`,
  `under_review`, `resolved`, `rejected`, `withdrawn` (member names upper-case, for example
  `DisputeState.UNDER_REVIEW`); add `StateChange` (`from_state: DisputeState`, `to_state:
  DisputeState`, `note: str | None`, `changed_at: datetime`); add `TransitionRequest` with
  `to_state: DisputeState` ("required, must be one of the five values (case-sensitive)") and `note:
  str | None = None` ("optional, at most 1000 characters as sent; empty or whitespace-only becomes
  null", so a validator returns `None` for a blank value and otherwise returns the value
  unchanged), with `extra="forbid"`; add to `Dispute` the fields `updated_at: datetime` (required)
  and `history: list[StateChange] = Field(default_factory=list)` (makes T003 pass)
- [X] T009 *(owner)* Create `src/disputes/transitions.py` with `ALLOWED_TRANSITIONS:
  dict[DisputeState, frozenset[DisputeState]]` exactly as in data-model.md (`open` →
  `{under_review, withdrawn}`, `under_review` → `{resolved, rejected, withdrawn}`, the three
  closed states → empty)
  and `is_allowed(from_state, to_state) -> bool`; no other place in the code may list the rules
  (makes T002 pass; needs T008)
- [X] T010 *(owner)* Edit `src/disputes/errors.py`: add `InvalidTransitionError(Exception)` that
  stores `from_state` (the state the dispute is in) and `to_state` and takes a keyword
  `state_changed: bool = False`; add a handler that returns HTTP 409 with the standard envelope,
  code `invalid_transition` and `details == []`, and two messages: by default `Cannot change state
  from {from} to {to}` (the state values, for example `resolved` and `rejected`); when
  `state_changed` is true, `The dispute changed to {from} while this request was being handled;
  read it again and retry if the move is still wanted`; register it in `register_error_handlers`
  (makes T004 pass; research.md section 4)
- [X] T011 *(owner)* Edit `src/disputes/routes.py`: in `create_dispute` take one `now =
  datetime.now(UTC)` and build the `Dispute` with `created_at=now`, `updated_at=now` and
  `history=[]` (makes T006 pass; the existing create tests must pass again too)
- [X] T012 Run `uv run pytest` and `uv run ruff check .`; T002 to T006 and every earlier test
  pass (green), lint clean

**Checkpoint**: Model, rules table and 409 error exist; user stories can begin

---

## Phase 3: User Story 1 - Move a dispute through its lifecycle (Priority: P1) MVP

**Goal**: `POST /disputes/{dispute_id}/transitions` applies a transition and returns the updated
dispute. In this phase the route does not yet check the rules (US2 adds that), so the branch is
not mergeable until US2 is done.

**Independent Test**: Create a dispute, post `under_review`, then `resolved`; after each step the
response is 200 and shows the new state.

### Tests first (must fail before T016 and T017)

- [X] T013 [US1] Extend `tests/test_repository.py` for the new operation
  `transition(dispute_id, from_state, to_state, note, at)`: (a) on a stored `open` dispute,
  `transition(id, OPEN, UNDER_REVIEW, "note", at)` with `at` later than the stored `updated_at`
  returns a dispute with state `under_review`, `updated_at == at`, and a history of exactly one
  entry `StateChange(open, under_review, "note", at)`; (b) `repository.get(id)` then returns an
  equal dispute; (c) the dispute object stored before the call is not mutated (its state is still
  `open` and its history empty); (d) when the
  stored state differs from `from_state`, it returns `None` and the stored dispute is unchanged;
  (e) an unknown id returns `None`; (f) `note=None` is recorded as `None`; (g) two successive
  calls build a history of two entries in order; (h) time never goes backwards (research.md
  section 6): on a stored dispute whose `updated_at` is `T`, `transition(..., at=T - 1 second)`
  succeeds, and both the returned `updated_at` and the new entry's `changed_at` equal `T`, not
  `T - 1 second`; a following call with `at=T + 1 second` gives `T + 1 second`; this simulates two
  requests that read the clock in one order and are applied in the other, without threads
- [X] T014 [US1] Write `tests/test_transition_dispute.py` (fresh repository per test through the
  `client` fixture, synthetic data `txn_0001`, `cust_0001`, helper that creates a dispute through
  `POST /disputes` and a helper that drives it to a given state through valid transitions): each
  of the 5 allowed transitions (`open→under_review`, `open→withdrawn`, `under_review→resolved`,
  `under_review→rejected`, `under_review→withdrawn`) returns 200 with the new `state` and the same
  `id`; a request with a note stores it and a request without a note stores `null` in the history
  entry; the 200 body equals the result of a following `GET /disputes/{id}`; two steps in a row
  (`open→under_review→resolved`) leave state `resolved`

### Implementation

- [X] T015 [US1] Run `uv run pytest`; confirm T013 and T014 fail (red: `transition` does not
  exist, the route returns 404 or 405)
- [X] T016 [US1] *(owner)* Edit `src/disputes/repository.py`: add `transition(dispute_id: UUID,
  from_state: DisputeState, to_state: DisputeState, note: str | None, at: datetime) -> Dispute |
  None` to the `DisputeRepository` protocol and to `InMemoryDisputeRepository`: read the stored
  dispute; return `None` if it is missing or its state is not `from_state`; otherwise build a new
  `Dispute` with `model_copy(update=...)`: compute `effective_at = max(at, current.updated_at)`
  once and use it for the new `updated_at` and for the new entry's `changed_at`; `history` = old
  history plus one `StateChange(from_state, to_state, note, effective_at)` as a new list; store
  it and return it. Add a one-line comment saying why `max` is used (the route reads the clock
  before the repository applies the change). No lock yet: the lock is added in US3 after a failing
  test (makes T013 pass)
- [X] T017 [US1] *(owner)* Edit `src/disputes/routes.py`: add `POST
  /disputes/{dispute_id}/transitions` with `dispute_id: UUID` and a body `TransitionRequest`; read
  the dispute with `repository.get` (assume it exists for now; US2 adds the 404), call
  `repository.transition(dispute_id, current.state, body.to_state, body.note,
  datetime.now(UTC))` and return the result with status 200; annotate the function's return type
  as `-> Dispute` so the generated OpenAPI documents the 200 response as the `Dispute` schema,
  which T020 asserts (makes T014 pass)
- [X] T018 [US1] Run `uv run pytest` and `uv run ruff check .`; T013 and T014 pass (green), all
  earlier tests still pass, lint clean

**Checkpoint**: User Story 1 works on its own. MVP (without rules yet)

---

## Phase 4: User Story 2 - Refuse invalid transitions and never reopen closed disputes (Priority: P1)

**Goal**: Only the 5 allowed transitions succeed. Every other request is refused in the standard
error format and leaves the dispute unchanged.

**Independent Test**: For all 25 state pairs, exactly the 5 allowed ones return 200 and the other
20 return 409 `invalid_transition` with the dispute unchanged.

### Tests first (must fail before T022)

- [X] T019 [P] [US2] Extend `tests/test_transition_dispute.py`: (a) parametrized over all 25
  (current state, requested state) pairs, drive a fresh dispute to the current state, post the
  requested state, and assert 200 for the 5 allowed pairs and for the other 20 a 409 with
  `error.code == "invalid_transition"`, `details == []` and a message containing both state
  names (SC-002); (b) after every refused request, `GET /disputes/{id}` returns a body identical to
  the one before the request: same `state`, `updated_at` and `history` (SC-003); (c) from each of
  `resolved`, `rejected` and `withdrawn`, a request for `open` returns 409 and the state stays
  (FR-003); (d) `to_state` `"closed"` and `"Resolved"` return 422 with a `details` entry whose
  `field` is `to_state`; a body `{}` returns 422 naming `to_state`; a body with an extra field
  `from_state` returns 422 naming `from_state`; a note of 1001 characters returns 422 naming
  `note`; a malformed JSON body returns 422 with `field == "body"`; a request with no body at
  all (POST without content) also returns 422 with `field == "body"`; (e) a well-formed id with no
  dispute returns 404 with `error.code == "not_found"`; `/disputes/not-a-uuid/transitions` returns
  422 naming `dispute_id`; (f) `GET /disputes/{id}/transitions` returns 405 with `error.code ==
  "method_not_allowed"`; (g) a refused request does not add a history entry; (h) lost race,
  deterministic *(AI may draft the wrapper)*: on an `open` dispute, replace
  `repository.transition` with a wrapper that first applies a competing real transition
  (`open→under_review`) and then calls the real one with the original arguments (`from_state` is
  now stale); a request for `withdrawn` returns 409 with `error.code == "invalid_transition"`, a
  message that contains `changed` and `under_review` and not `Cannot change state`, and a later
  `GET` shows state `under_review` with exactly one history entry (the competing one); this is
  the only test that reaches the `None` branch of the route without relying on timing
- [X] T020 [P] [US2] Extend `tests/test_openapi.py`: the transitions operation documents `200`
  (reference to `Dispute`), and `404`, `409` and `422` each with the `ErrorResponse` schema;
  `TransitionRequest` is in the schema, requires `to_state` and has no other required field

### Implementation

- [X] T021 [US2] Run `uv run pytest`; confirm the refusal and validation cases in T019 and T020
  fail (red: every request is accepted, the unknown id raises, `409` is not documented). Record
  which cases already pass and why (for example the 422 cases and the 405 are already produced by
  the framework and the handlers from feature 001); those only guard against regressions
- [X] T022 [US2] *(owner)* Edit `src/disputes/routes.py`: in the transitions route, raise
  `DisputeNotFoundError` when `get` returns `None`; raise `InvalidTransitionError(current.state,
  body.to_state)` when `is_allowed(current.state, body.to_state)` is false; when
  `repository.transition(...)` returns `None` (the state changed after the read), read the dispute
  again and raise `InvalidTransitionError(state_it_is_in_now, body.to_state, state_changed=True)`,
  not the "not allowed" message, because the move may be allowed from the new state; declare
  `responses` for `404`, `409` and `422` with the `ErrorResponse` model and a description
  (research.md sections 2 and 4)
- [X] T023 [US2] Run `uv run pytest` and `uv run ruff check .`; T019 and T020 pass (green), all
  earlier tests still pass, lint clean

**Checkpoint**: User Stories 1 and 2 work; the branch is now safe to merge as far as single
requests go

---

## Phase 5: User Story 3 - Resolve concurrent transitions safely (Priority: P1)

**Goal**: When incompatible transitions reach the same dispute at the same time, exactly one wins
and the other gets 409; a final state is never overwritten.

**Independent Test**: Repeat a race of resolve vs reject on the same dispute at least 50 times;
every round has exactly one 200, one 409, and the final state is the winner's.

### Tests first (must fail before T027)

- [X] T024 [P] [US3] Extend `tests/test_repository.py` with the test
  `test_transition_is_atomic_under_a_slow_read` *(AI may draft the scaffolding)*: define a
  `dict` subclass `SlowDict` whose `get` and `__getitem__` call `time.sleep(0.05)` before
  answering; set `repository.disputes = SlowDict()`; store one `open` dispute; start 8 threads
  released together by a `threading.Barrier(8)`, each
  calling `repository.transition(id, OPEN, UNDER_REVIEW, None, now)`; assert exactly one call
  returned a dispute and 7 returned `None`, and the stored history has exactly one entry. Add a
  second test: 8 threads each transition a different open dispute; all 8 succeed (FR-015)
- [X] T025 [P] [US3] Write `tests/test_transition_concurrency.py` *(AI may draft the thread
  harness)*: a helper fires two POSTs at once for one dispute using `ThreadPoolExecutor(2)` and a
  `threading.Barrier(2)` that each worker passes just before calling `client.post`, with one
  shared `TestClient` (each request gets its own event loop, plan research section 3); each case
  runs 50 rounds with a fresh dispute per round: from `under_review`, the pairs (`resolved`,
  `rejected`), (`withdrawn`, `resolved`) and (`withdrawn`, `rejected`) give exactly one 200 and
  one 409 per round and the final `state` equals the `to_state` of the 200 (SC-004, SC-005); from
  `open`, two identical `under_review` requests give exactly one 200 and one 409; from `open`,
  the pair (`under_review`, `withdrawn`) ends in one of three outcomes: `under_review` wins and
  `withdrawn` gets 409, `withdrawn` wins and `under_review` gets 409, or both succeed with the
  final state `withdrawn`; in every round of every case the history forms an unbroken chain (first
  `from_state` is `open`, each `from_state` equals the previous `to_state`, the last `to_state`
  equals `state`, last `changed_at` equals `updated_at`) and time never goes backwards
  (`created_at <= history[0].changed_at <= ... <= history[-1].changed_at == updated_at`); 10
  identical requests at once on one `open` dispute give exactly one 200 and nine 409 and one
  history entry; transitions on two
  different disputes at once both succeed; on an already closed dispute (SC-005, FR-014): for each
  of `resolved`, `rejected` and `withdrawn`, 50 rounds of 3 simultaneous requests for the other
  two closed states and for `open` (use `ThreadPoolExecutor(3)` and `Barrier(3)`) all return 409,
  and afterwards the dispute's `state`, `updated_at` and `history` are identical to before the
  round

### Implementation

- [X] T026 [US3] Run `uv run pytest tests/test_repository.py tests/test_transition_concurrency.py`;
  confirm `test_transition_is_atomic_under_a_slow_read` fails because several threads succeed
  (red). Record honestly whether T025 already passes without a lock: it may, because a barrier
  cannot force the handlers to interleave; T024 is the proof that the lock is needed
- [X] T027 [US3] *(owner)* Edit `src/disputes/repository.py`: give `InMemoryDisputeRepository` a
  `threading.Lock`, and hold it during the whole check-and-write in `transition` and during
  `add`; `get` stays lock-free (research.md section 2). Add a one-line comment saying why the
  lock exists (makes T024 pass)
- [X] T028 [US3] Run `uv run pytest` and `uv run ruff check .`; T024 and T025 pass (green); then
  run `uv run pytest tests/test_transition_concurrency.py tests/test_repository.py` five more
  times and confirm it passes every time (a single pass is not enough evidence for a race test);
  record the result.
  **Result (2026-11-15):** 233 tests pass, lint clean; the concurrency file plus the repository
  tests passed in 5 of 5 repeats, and in 45 earlier repeats (30 full, 15 of the closed-dispute
  test alone). Two earlier repeats **hung** (no failure, no output) in
  `test_a_closed_dispute_is_never_changed_by_simultaneous_requests` while the main thread waited
  in `race`; the cause was not found and it did not reproduce in the later repeats. Those
  requests are refused by the rules before the repository lock is reached. `race` now has a
  20 s timeout so a hang fails with a message instead of blocking the run.

**Checkpoint**: User Stories 1 to 3 work; concurrent requests cannot produce an invalid state

---

## Phase 6: User Story 4 - See when a dispute changed and why (Priority: P2)

**Goal**: Every dispute shows `updated_at` and an ordered `history` of its successful changes.

**Independent Test**: Move a dispute through two transitions with notes, fetch it, and see both
entries in order and `updated_at` equal to the last entry's `changed_at`.

### Tests first (must fail before T033)

- [X] T029 [P] [US4] Extend `tests/test_get_dispute.py`: a fetched new dispute has `updated_at ==
  created_at` and `history == []`; a fetched dispute after a transition shows the new `updated_at`
  and one history entry
- [X] T030 [US4] Extend `tests/test_transition_dispute.py`: after two transitions with notes
  (`under_review` with a note, then `resolved` with another), `GET /disputes/{id}` returns
  `history` with two entries in order, each with `from_state`, `to_state`, `note` and a
  timezone-aware `changed_at`, the first `from_state` is `open`, the second `from_state` equals the
  first `to_state`, `history[-1].changed_at == updated_at`, `updated_at >= created_at` (not
  strictly greater: on this machine 200,000 consecutive `datetime.now(UTC)` calls returned only 44
  distinct values, so two nearby timestamps are often equal; research.md section 6), and
  `changed_at` values do not decrease (SC-006); the order of the entries, not their timestamps,
  proves the sequence; a refused transition leaves `updated_at` and `history` identical
- [X] T031 [P] [US4] Extend `tests/test_openapi.py`: the generated `Dispute` schema lists
  `updated_at` and `history` as required, a `StateChange` schema exists with `from_state`,
  `to_state`, `note` and `changed_at`, and the `DisputeState` schema lists the five values

### Implementation

- [X] T032 [US4] Run `uv run pytest`; record which of T029 to T031 fail and which already pass and
  why (the create route, the repository and the handlers already set and return the values from
  T008, T011 and T016; the OpenAPI "required" check is the one most likely to fail)
  **Result (2026-11-15):** none of T029 to T031 failed: all 8 new tests passed on the first run
  (241 passed). The values were already produced by US1 and US2, and `Dispute` already had
  `json_schema_serialization_defaults_required=True`, so `history` and `updated_at` are marked
  required. To check the tests are not vacuous, `history` was hidden from responses for one run:
  10 tests failed, including the US4 ones; the change was then reverted
- [X] T033 [US4] *(owner)* (no change needed, see the T032 result) Fix whatever T032 shows failing, only in the files that cause it (for
  example `model_config` of `Dispute` in `src/disputes/models.py` so that `history` is marked
  required in the generated schema); if nothing fails, record that no change was needed
- [X] T034 [US4] Run `uv run pytest` and `uv run ruff check .`; T029 to T031 pass (green), all
  earlier tests still pass, lint clean

**Checkpoint**: User Stories 1 to 4 work

---

## Phase 7: User Story 5 - Use the renamed reason (Priority: P3)

**Goal**: `refund_not_received` replaces `devolution` in dispute creation.

**Independent Test**: Create a dispute with `refund_not_received` (201) and one with `devolution`
(422 naming `reason`).

### Tests first (must fail before T038)

- [X] T035 [P] [US5] Edit `tests/test_models.py`: `test_reason_values_match_the_contract` expects
  `duplicate_charge`, `unrecognized_charge`, `product_not_received`, `incorrect_amount`,
  `refund_not_received`; `DisputeCreate` with reason `"devolution"` raises `ValidationError`
- [X] T036 [P] [US5] Edit `tests/test_create_dispute.py`: the test that creates one dispute per
  reason uses `refund_not_received` in place of `devolution`; add a test that `"devolution"`
  returns 422 with a `details` entry whose `field` is `reason` and that `repository.disputes` stays
  empty

### Implementation

- [X] T037 [US5] Run `uv run pytest`; confirm T035 and T036 fail (red)
- [X] T038 [US5] *(owner)* Edit `src/disputes/models.py`: replace `Reason.DEVOLUTION =
  "devolution"` with `Reason.REFUND_NOT_RECEIVED = "refund_not_received"`; no alias for the old
  value (research.md section 8) (makes T035 and T036 pass)
- [X] T039 [US5] Search `src/` and `tests/` for `devolution` and `DEVOLUTION`; the only matches
  allowed are the two tests that check the old value is rejected; run `uv run pytest` and
  `uv run ruff check .` (green, lint clean). Feature 001's files under `specs/001-*` are left
  unchanged on purpose

**Checkpoint**: All five user stories work

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T040 [P] Compare `/openapi.json` from the running app with
  `specs/002-dispute-state-transitions/contracts/disputes.openapi.yaml` (paths, status codes,
  schemas, enum values, required fields, the `invalid_transition` code); fix whichever is wrong,
  with a test in `tests/test_openapi.py` for anything fixed in code; record known differences left
  on purpose (feature 001 left `amount` accepting a JSON number)
  **Result (2026-11-15):** compared with a script on `app.openapi()` (the app object, not a
  server). Paths, methods, status codes, the `Reason` and `DisputeState` enums, required fields
  and `additionalProperties: false` match. Two contract errors fixed in the contract (no code
  change, so no new test): `Dispute` now lists `description` as required (the API always returns
  it, `null` when empty), and the error `code` is no longer a closed enum (the framework fallback
  `http_error` was missing). Differences left on purpose: `amount` is generated as number or
  string (feature 001); `/health` is outside this contract; the generated `Dispute` is one flat
  schema where the contract uses `allOf`; `note` is generated as `anyOf` string or null
- [X] T041 [P] *(AI may draft)* Update `README.md` in the language the file already uses (Spanish
  today): do not translate the rest of the file and do not mix languages inside a section; the full
  translation of the README to English is a separate change. Content: the endpoint table gains
  `POST /disputes/{id}/transitions` (200, 404, 409, 422); describe the five states and the 5 allowed
  transitions; `updated_at` and `history` in the response; the reason list with
  `refund_not_received`; the limits: storage is in memory, atomic transitions hold only inside one
  running process, no authentication; mark roadmap item 1 as done (create, get, change state);
  describe the concurrency tests for what they prove and what they cannot (the barrier cannot force
  an interleaving; the slow-read test does). Claim nothing else (constitution principle VI)
- [X] T042 [P] *(AI may draft)* Update `docs/ARCHITECTURE.md`: in the component diagram and
  section 3, change the transitions from Planned to Exists and add `transitions.py`; remove "The
  only state is `open`" from the current limits; add the single-process limit of the lock; in the
  design table set the two transition rows to Exists and add rows for compare-and-set without
  retry and embedded history; point the contract row to the 002 contract
- [X] T043 Update `CLAUDE.md` at "Al cerrar una feature": "Estado actual" (feature 002 done, next
  is the Dockerfile and image in CI, then 003), the roadmap table (002 Hecha), and "Decisiones ya
  tomadas" with what was confirmed: the five allowed transitions, `under_review→withdrawn` yes,
  `open→rejected` no, `refund_not_received`, `updated_at`, embedded history, compare-and-set with
  no retry; remove the "Feature 002" section and its open decisions
- [X] T044 Walk through every command in `specs/002-dispute-state-transitions/quickstart.md`
  against a running server (`uv run uvicorn disputes.main:app --reload`) and confirm the expected
  statuses and bodies; record the date and the result
  **Result (2026-11-15):** all 12 checks passed against a real `uvicorn` process (port 8765) using
  `curl`: create (201, `updated_at == created_at`, empty history), under_review (200, one entry
  from `open`), skipping a step (409 `invalid_transition`, dispute unchanged), close (200) and
  reopen (409), history in order with `updated_at` equal to the last `changed_at`, three 422
  bodies, unknown id (404) and the old reason `devolution` (422 naming `reason`). The script's
  `terminate()` stopped only the `uv` wrapper and left the `uvicorn` child listening on 8765;
  it was found afterwards and killed by hand (port free). Not walked: the racing commands (covered by the tests, not by hand)
- [X] T045 Final run of `uv run pytest` and `uv run ruff check .`; run
  `uv run pytest tests/test_transition_concurrency.py tests/test_repository.py` five more times
  and record that all runs pass; record the total number of tests; confirm no real data or
  secrets are in any new or changed file (principle III) and that every id used is synthetic
  **Result (2026-11-15):** 243 tests pass, lint clean. The concurrency file plus the repository
  tests passed in 5 of 5 repeats (23 tests each). Total of repeats with no hang since the
  timeout was added: 5; the two earlier hangs (see T028) are still unexplained. Scan of the 19
  changed or new files: no keys, secrets or e-mail addresses; the only identifiers are
  `txn_0001` and `cust_0001`. The scan was first run over the wrong file list (it missed staged
  files) and was repeated over `git status`
- [X] T046 Before committing, the owner reads every changed file and can explain each line
  (CLAUDE.md rule); then open a PR from `feat/002-dispute-state-transitions` into `develop` and
  confirm CI is green on the PR before merging (constitution, Development Workflow)
  **Result (2026-11-16):** marked done by the owner. Walked through with the assistant:
  `transitions.py` (rules table) and the lock in `repository.py`. The rest of the changed files
  (`models.py`, `routes.py`, `errors.py`, the tests) the owner studies alone

---

## Dependencies & Execution Order

- Phase 1 first, then Phase 2 (blocks everything), then US1, US2, US3, US4, US5, then Phase 8.
- US1 needs Phase 2. US2 builds on the route from US1 (it adds the 404, the rules check and the
  409 mapping). US3 builds on the `transition` operation from US1 (it adds the lock) and on the
  route from US2 for the HTTP-level tests. US4 and US5 need Phase 2 and are independent of each
  other; US4 reads values already produced by US1.
- In Phase 2, T009 needs the states from T008, and T010 needs them for its message; do T008 first.
- Within each phase: tests, then the red run, then implementation, then the green run.
- The branch must not be merged between US1 and US2 (the route has no rules check yet).
- Phase 8: T040 to T042 need all stories done; T043 after T041 and T042; T044 to T046 last.

## Parallel Opportunities

- T002, T003, T004, T005 and T006 (different test files)
- T019 and T020 (different test files)
- T024 and T025 (different test files)
- T029 and T031 (different test files); T030 edits `tests/test_transition_dispute.py`, the same
  file as T019, so it is not marked `[P]` and runs on its own
- T035 and T036 (different test files)
- T040, T041 and T042 (different files)

## Implementation Strategy

- **MVP**: Phase 1, Phase 2 and US1 (T001 to T018): a client can move a dispute from one state to
  another and get the updated dispute. Not yet safe to merge: there is no rules check until US2.
- **Increment 2**: US2 (rules, 409, 404), then US3 (the lock, proven by a failing test first).
  After US3 the core of the feature is done.
- **Increment 3**: US4 (updated_at and history verified through the API), then US5 (the rename),
  then Phase 8 (contract check, docs, PR).
- Commit after each green checkpoint, with a conventional message, and only after the owner can
  explain the code. Do not combine a red test task and its implementation in one commit step.
