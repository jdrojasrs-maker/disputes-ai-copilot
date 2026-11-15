# Research: Dispute State Transitions

No `NEEDS CLARIFICATION` items remained in the Technical Context. The items below are the
decisions the spec deferred to planning.

## 1. Where the transition rules live

- **Decision**: A new module `src/disputes/transitions.py` holds one table,
  `ALLOWED_TRANSITIONS: dict[DisputeState, frozenset[DisputeState]]`, and one function,
  `is_allowed(from_state, to_state) -> bool`. Terminal states map to an empty set.
- **Rationale**: Constitution II and FR-004 require the rules in one place. A table is data, so the
  test can check all 25 pairs against it, and nobody has to read `if` chains to learn the rules.
- **Alternatives considered**: Methods on the `Dispute` model (rejected: mixes rules with data
  shape); `if/elif` in the route (rejected: rules spread over request handling).

## 2. Atomic transition (the core of FR-014)

- **Decision**: The repository gets one operation:
  `transition(dispute_id, from_state, to_state, note, at) -> Dispute | None`. It changes the
  dispute to `to_state` only if its current state is still `from_state`, in one step, and returns
  the updated dispute; otherwise it changes nothing and returns `None`. The in-memory
  implementation does the check and the write inside `with self._lock:` (`threading.Lock`).
  The route does: `get` (404 if missing) → `is_allowed(current.state, to_state)` (409 if not) →
  `transition(...)` → if it returns `None`, re-read the dispute and answer `409` naming the state
  it is in now.
- **Rationale**: A read followed by a write is a race: two requests can both read `open` and both
  write. The check and the write must be one indivisible step. The routes are plain `def`
  functions, so FastAPI runs them in a thread pool and they really overlap; a `threading.Lock`
  is the right tool (an `asyncio.Lock` would not protect threads). In PostgreSQL the same
  operation is `UPDATE disputes SET state = :to WHERE id = :id AND state = :from`, where "0 rows
  updated" means conflict, so the route does not change when the repository is swapped.
- **No retry**: If the compare-and-set fails because the state changed after the route read it,
  the request is refused with `409`, not re-evaluated. Retrying would hide conflicts and make
  results depend on timing. The spec allows this (FR-014: a request whose starting state changed
  MAY be refused). The caller can read the dispute again and decide.
- **What is guaranteed**: Every recorded change is a valid transition from the state the dispute
  was really in, and each history entry's `from_state` equals the previous entry's `to_state`.
  Two requests that can never both succeed (resolve and reject) never both succeed.
- **Alternatives considered**: One lock around the whole route (rejected: serializes unrelated
  disputes, violates FR-015); a version number on the dispute (rejected: not needed, the state is
  the guard; a version arrives only if a later feature needs it); retry loop (rejected, above);
  per-dispute locks (rejected: more code for no benefit at this scale).
- **Limit stated in the docs**: The lock protects one process. With several workers each has its
  own memory and its own lock; that is the existing in-memory limit, and PostgreSQL fixes it.

## 3. How concurrency is tested

- **Decision**: Two layers.
  1. **Repository, deterministic**: a test replaces `repository.disputes` with a dict subclass whose
     `get` sleeps briefly before answering. Without the lock, two threads both read `open` during
     that pause and both write, so both calls return a dispute and the test fails (red). With the
     lock, exactly one returns a dispute. This proves the lock is necessary and is the red step
     for the implementation.
  2. **HTTP, statistical**: `ThreadPoolExecutor` plus `threading.Barrier` fire two requests at
     once through `TestClient`, repeated for at least 50 rounds with a fresh dispute each time.
     Pairs: resolve vs reject, withdraw vs resolve, withdraw vs reject (from `under_review`), and
     two identical requests. For these exactly one `200` and one `409` per round, and the final
     state matches the winner (SC-004). The pair `under_review` vs `withdrawn` from `open`
     can legitimately end three ways (spec, story 3, scenario 2), so the test asserts the outcome
     is one of those and that the history forms an unbroken chain.
- **Verified**: Starlette's `TestClient` (1.10.0 here) opens its own event loop per request when
  it is not used as a context manager, so threads sharing one client send truly overlapping
  requests.
- **Honest limit**: The barrier starts the requests together but cannot force the handlers to
  interleave. The HTTP rounds therefore check safety (no invalid result in any round); only layer
  1 forces the race. Both are reported as such in the README.
- **Alternatives considered**: Only HTTP-level tests (rejected: could pass without the lock);
  mocking the lock (rejected: tests the mock).

## 4. Error for a refused transition

- **Decision**: HTTP `409`, error code `invalid_transition`, message such as
  `Cannot change state from resolved to rejected`, `details` empty. New `InvalidTransitionError`
  carries the two states; a handler in `errors.py` builds the same envelope as the other errors.
  The code list in the contract becomes `validation_error`, `not_found`, `method_not_allowed`,
  `invalid_transition`.
- **Two messages, one code**: A move refused by the rules says `Cannot change state from
  {current} to {requested}`. A request that lost a race (the repository returned `None` because
  the state changed after the route read it) says `The dispute changed to {current} while this
  request was being handled; read it again and retry if the move is still wanted`.
  `InvalidTransitionError` takes `state_changed=True` for the second case. Both are `409` with
  the code `invalid_transition`.
- **Rationale**: The client reaction is the same (read the dispute again and decide), so one code
  is enough. The messages differ because the first one would be false for a lost race: after the
  winner moved `open` to `under_review`, "withdrawn" is allowed from the new state, and saying
  "cannot change state from under_review to withdrawn" would mislead. `details` stays empty
  because the cause is a state relationship, not a malformed field; the spec states this in
  FR-009.
- **Alternatives considered**: Generic code `conflict` (rejected: less informative); a different
  code for a lost race (rejected: the client reaction is the same; only the message differs).
- **How it is tested**: the lost-race branch is reached deterministically by wrapping
  `repository.transition` so that a competing transition is applied just before the real call
  (tasks.md, T019 (h)); the threaded tests cannot reach it on demand.

## 5. History: shape and where it is read

- **Decision**: `Dispute.history` is an embedded list of `StateChange` objects, oldest first:
  `from_state`, `to_state`, `note` (or `null`), `changed_at` (UTC). A new dispute has `[]`. No
  separate endpoint.
- **Rationale**: One object means one atomic replacement under the lock, a self-contained response
  (`POST .../transitions` returns the dispute with its history), and fewer routes to test.
  FR-013 only requires that the history be readable through the API.
- **Alternatives considered**: `GET /disputes/{id}/history` (rejected for now: extra route and
  extra 404/422 cases for no current need; can be added when a dispute can accumulate a long
  history or when PostgreSQL stores it in its own table).

## 6. `updated_at` and timestamps

- **Decision**: `updated_at` is required on `Dispute`, set equal to `created_at` on creation, and
  set on every successful transition. The route creates one `datetime.now(UTC)` and passes it as
  `at`. Inside the lock, `transition` computes `effective_at = max(at, current.updated_at)` and
  uses that single value for both the new history entry's `changed_at` and `updated_at`, so they
  are always equal (SC-006) and never move backwards (FR-011, FR-013).
- **Why not use `at` as is**: The route takes its clock reading before the repository's lock.
  Request A can read the clock (t1), request B can read it later (t2 > t1), B can then win the
  lock and be applied first, and A is applied second with t1. The history would list B's change
  (t2) before A's (t1) and `updated_at` would go back from t2 to t1. This can happen whenever two
  requests are both applied in a row (for example `open→under_review` and then
  `under_review→withdrawn` arriving together). Taking the later of the two values inside the lock
  fixes the order without a second clock reading; the order of the history entries is the order
  of application.
- **Rationale**: One value per operation removes any chance of `changed_at` and `updated_at`
  differing, and the lock makes "later than the previous change" a check made at the moment of
  writing.
- **Alternatives considered**: Reading the clock inside the repository (rejected: tests could no
  longer pass a fixed `at`, and the route and repository would each own a clock); a per-dispute
  sequence number (rejected: not needed, the order of the list already is the sequence).
- **Consequence**: Existing tests that build a `Dispute` directly must pass `updated_at`. This is
  an expected red-then-green change.
- **Clock resolution (measured)**: On the development machine (Python 3.12.15, Windows), 200,000
  consecutive `datetime.now(UTC)` calls returned only 44 distinct values, with a smallest step of
  about 0.54 ms. Two timestamps taken close together are therefore often equal. Tests compare
  `updated_at >= created_at` and `changed_at` non-decreasing, never strictly greater, and prove
  the order of changes by the order of the history entries. Linux CI may have a finer clock; the
  tests must not depend on it.

## 7. The note

- **Decision**: `note` is `str | None`, maximum 1000 characters as sent. A value that is empty or
  only whitespace becomes `None`; any other value is stored exactly as sent. A longer note is a
  `422` naming `note`.
- **Rationale**: Matches the spec assumption (same limit as `description`). Not trimming non-blank
  notes keeps "stored as sent" true.

## 8. Renaming the reason

- **Decision**: `Reason.DEVOLUTION` is replaced by `Reason.REFUND_NOT_RECEIVED =
  "refund_not_received"`. There is no alias for the old value, so `devolution` fails validation.
- **Rationale**: FR-016 says the old value must be rejected. No data exists to migrate (in-memory
  storage).
- **Contract and old specs**: The file `contracts/disputes.openapi.yaml` in this feature describes
  the whole current API (create, get and transitions), so it replaces feature 001's contract as
  the current one. The 001 files are left untouched: they are the record of what that feature
  delivered, and still mention `devolution` for that reason.

## 9. Consistency fix made in the spec during planning

- **Finding**: With `under_review → withdrawn` allowed (clarification of 2026-11-15), the spec's
  original wording for the race between "take under review" and "withdraw" on an `open` dispute
  ("exactly one succeeds") was no longer always true: both can succeed in order.
- **Change**: Story 3 scenario 2 and FR-014 were reworded to the guarantee that holds: every
  applied change is valid from the state the dispute was really in, and requests that can never
  both succeed (resolve vs reject) give exactly one success. The SC-004 race (resolve vs reject)
  was already of that kind and is unchanged.

## 10. Dependencies

- **Decision**: No new dependency. Threads and barriers come from the standard library.
