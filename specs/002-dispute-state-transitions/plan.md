# Implementation Plan: Dispute State Transitions

**Branch**: `feat/002-dispute-state-transitions` | **Date**: 2026-11-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-dispute-state-transitions/spec.md`

## Summary

Add `POST /disputes/{dispute_id}/transitions`, which moves a dispute through five states
(`open`, `under_review`, `resolved`, `rejected`, `withdrawn`). The five allowed transitions live
in one table in a new domain module (FR-002, FR-004). A refused transition returns `409` with the
existing error envelope and changes nothing (FR-007, FR-009). Each dispute gains `updated_at` and
an embedded, ordered `history` of state changes (FR-011 to FR-013). Concurrency is handled by one
atomic compare-and-set operation in the repository: "change to X only if the current state is Y",
guarded by a lock in the in-memory implementation (FR-014). The reason `devolution` is renamed to
`refund_not_received` (FR-016). See [research.md](research.md) for the decisions.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, Pydantic v2 (already in `pyproject.toml`); no new
dependencies (`threading` and `concurrent.futures` are standard library)

**Storage**: In-memory repository, unchanged in kind. The new repository operation is designed so
that PostgreSQL can implement it as `UPDATE ... WHERE id = :id AND state = :expected` in the
persistence feature

**Testing**: pytest with FastAPI `TestClient` (as in feature 001) plus threads for the
concurrency tests; ruff for lint

**Target Platform**: Linux server (Docker Compose locally), developed on Windows

**Project Type**: web-service (single project)

**Performance Goals**: None specified; interactive latency is enough

**Constraints**: Tests written first (red, then green); synthetic data only; one error format;
guarantees hold per running process (routes are synchronous and run in a thread pool, so
requests really do overlap inside one process)

**Scale/Scope**: 1 new endpoint, 1 new domain module, 2 new model types (`StateChange`,
`TransitionRequest`) and 2 changed ones (`Dispute`, `DisputeState`), 1 new repository operation,
1 new error type

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| I. Tests first | Pass | Tests are listed before source files and tasks will order red before green. The lock is proven necessary by a test that fails without it (research.md, section 3) |
| II. Valid state transitions | Pass | Allowed transitions are defined once in `transitions.py`. All 25 state pairs are tested: 5 allowed, 20 refused with the dispute unchanged. Closed states never reopen |
| III. Synthetic data only | Pass | Fixtures keep using fake ids such as `txn_0001`, `cust_0001`; notes in tests are invented text |
| IV. Validate at the boundary | Pass | `TransitionRequest` (Pydantic) validates the body before the domain runs; `409` uses the same error envelope as every other error |
| V. Independent service | Pass | No Bank access; nothing changes about how transaction ids are treated |
| VI. Honest documentation | Pass | README and `docs/ARCHITECTURE.md` will say that atomicity holds inside one process only and that storage is still in memory |

**Post-design re-check**: Pass. The design adds no dependency, no persistence and no Bank access.
The one design risk, claiming more concurrency safety than exists, is handled by stating the
single-process limit in the docs.

## Project Structure

### Documentation (this feature)

```text
specs/002-dispute-state-transitions/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── disputes.openapi.yaml   # Phase 1 output: the full current API contract
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/disputes/
├── main.py              # unchanged
├── models.py            # changed: DisputeState gets 5 values; Reason rename; new StateChange and
│                        #   TransitionRequest; Dispute gets updated_at and history
├── transitions.py       # new: ALLOWED_TRANSITIONS table and is_allowed()
├── repository.py        # changed: DisputeRepository.transition() (compare-and-set) + in-memory
│                        #   implementation with a lock
├── errors.py            # changed: InvalidTransitionError and its 409 handler
└── routes.py            # changed: POST /disputes/{dispute_id}/transitions; create sets updated_at

tests/
├── conftest.py                       # unchanged
├── test_models.py                    # changed: reason rename, TransitionRequest rules, Dispute fields
├── test_transitions.py               # new: the 5x5 table (SC-002)
├── test_repository.py                # changed: transition() and the lock test
├── test_create_dispute.py            # changed: refund_not_received, updated_at, empty history
├── test_get_dispute.py               # changed: new fields present
├── test_transition_dispute.py        # new: success, refusals, history, updated_at, errors
├── test_transition_concurrency.py    # new: parallel requests, repeated rounds (SC-004, SC-005)
├── test_error_format.py              # changed: the 409 envelope
└── test_openapi.py                   # changed: the new endpoint's documented responses

README.md                # changed: endpoints, limits, roadmap
docs/ARCHITECTURE.md     # changed: transitions and atomicity move from Planned to Exists
```

**Structure Decision**: Keep the flat `src/disputes` layout. The rules get their own small module
(`transitions.py`) so that "defined in one place in the domain" is literally one file the owner can
read in one minute; everything else extends existing modules.

## Complexity Tracking

No constitution violations; nothing to justify.
