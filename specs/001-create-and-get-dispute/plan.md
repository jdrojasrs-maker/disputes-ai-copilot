# Implementation Plan: Create and Get Dispute

**Branch**: `feat/001-create-and-get-dispute` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-create-and-get-dispute/spec.md`

## Summary

Add two endpoints to the existing FastAPI service: `POST /disputes` opens a dispute and
`GET /disputes/{dispute_id}` fetches it. Pydantic v2 models validate all input at the boundary
(FR-002 to FR-005, FR-007). New disputes always start `open`. All errors share one JSON shape
(FR-012). Storage is an in-memory repository behind a small interface, because PostgreSQL and
Alembic arrive in a later feature (constitution, Technical Constraints). See
[research.md](research.md) for the decisions.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, Pydantic v2 (both already in `pyproject.toml`); no new
dependencies

**Storage**: In-memory repository for this feature (no persistence across restarts); PostgreSQL
replaces it in a later feature behind the same interface

**Testing**: pytest with FastAPI `TestClient` (httpx already in the dev group); ruff for lint

**Target Platform**: Linux server (Docker Compose locally), developed on Windows

**Project Type**: web-service (single project)

**Performance Goals**: None specified; interactive-latency behavior is enough for this feature

**Constraints**: Tests written first (red, then green); synthetic data only; one error format

**Scale/Scope**: 2 endpoints, 1 entity, 1 enum for reason, 1 enum for state

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| I. Tests first | Pass | Test files are listed before source files; tasks will order red before green |
| II. Valid state transitions | Pass (N/A) | Only the initial state `open` exists; no transitions are added (FR-013). Transition rules arrive in a later feature |
| III. Synthetic data only | Pass | All fixtures use fake ids such as `txn_0001`, `cust_0001` |
| IV. Validate at the boundary | Pass | Pydantic models validate input; one error envelope for validation, not-found and domain errors |
| V. Independent service | Pass | No Bank access; transaction ids are not verified against Bank |
| VI. Honest documentation | Pass | README will not claim persistence; docs will state storage is in-memory |

**Post-design re-check**: Pass. The design in Phase 1 adds no dependency, no persistence claim
and no state transition.

## Project Structure

### Documentation (this feature)

```text
specs/001-create-and-get-dispute/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── disputes.openapi.yaml   # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/disputes/
├── main.py              # existing; registers router and error handlers
├── models.py            # new: Reason, DisputeState, DisputeCreate, Dispute
├── repository.py        # new: DisputeRepository protocol + InMemoryDisputeRepository
├── errors.py            # new: error envelope model and exception handlers
└── routes.py            # new: POST /disputes, GET /disputes/{dispute_id}

tests/
├── test_health.py       # existing
├── test_models.py       # new: validation rules
├── test_repository.py   # new: save and get
├── test_create_dispute.py   # new: POST behavior
├── test_get_dispute.py      # new: GET behavior
└── test_error_format.py     # new: one envelope for every error kind
```

**Structure Decision**: Keep the existing single-project `src/disputes` layout and add flat
modules. A deeper package structure is not justified for one entity and two endpoints.

## Complexity Tracking

No constitution violations; nothing to justify.
