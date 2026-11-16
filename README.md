# Disputes AI Copilot

![CI](https://github.com/jdrojasrs-maker/disputes-ai-copilot/actions/workflows/ci.yml/badge.svg)

A **FastAPI** service for transaction disputes (a customer contests a charge), with an AI copilot planned on top: free-text intake, answers grounded in policy documents with citations, and an agent that can look up dispute and transfer state.

It is the AI half of a two-part system. **Bank** (a separate .NET, event-driven project) is the system being operated; this service is the copilot that helps operate it. The two are independent.

> **Status: work in progress.** A personal learning and portfolio project. All data is synthetic. Everything marked "Planned" does not exist yet.

## What exists today

Four endpoints, covered by automated tests:

| Method and path | What it does | Responses |
|---|---|---|
| `POST /disputes` | Opens a dispute. It always starts in state `open`. | `201` with the dispute and a `Location` header; `422` on invalid input |
| `GET /disputes/{dispute_id}` | Fetches a dispute by id. | `200`; `404` if it does not exist; `422` if the id is not a UUID |
| `POST /disputes/{dispute_id}/transitions` | Moves a dispute to another state, with an optional `note`. Returns the updated dispute. | `200`; `404` if it does not exist; `409` if the move is not allowed or the state changed while the request was handled; `422` on an invalid body or id |
| `GET /health` | Liveness check. | `200` |

Input fields: `transaction_id`, `customer_id`, `amount` (greater than 0, up to 2 decimals and 12 digits), `currency` (3 uppercase letters), `reason` (`duplicate_charge`, `unrecognized_charge`, `product_not_received`, `incorrect_amount`, `refund_not_received`) and an optional `description` (up to 1000 characters). Unknown fields, such as `state`, are rejected.

A dispute has one of five states: `open`, `under_review`, `resolved`, `rejected`, `withdrawn`. Exactly five moves are allowed:

```text
open         -> under_review | withdrawn
under_review -> resolved | rejected | withdrawn
```

`resolved`, `rejected` and `withdrawn` are final: a closed dispute never reopens, and a move to the current state is refused. Any other move returns `409` with the code `invalid_transition` and leaves the dispute unchanged. The rules live in one table in `src/disputes/transitions.py`.

Every dispute response also carries `updated_at` (equal to `created_at` until the first change) and `history`, the list of successful state changes, oldest first. Each entry has `from_state`, `to_state`, `note` and `changed_at`. A refused request adds no entry.

Every error uses the same format, including unknown routes and wrong methods:

```json
{"error": {"code": "validation_error", "message": "Request validation failed",
           "details": [{"field": "amount", "message": "Input should be greater than 0"}]}}
```

**Current limits:**
- Disputes are stored **in memory**: they are lost on restart, and with several worker processes each process has its own copy.
- A transition is atomic (a lock inside the in-memory repository) only within one process. With several worker processes each has its own memory and its own lock; PostgreSQL (feature 006) is what removes that limit.
- No authentication, and the referenced transaction is not checked to exist.
- No AI components yet.

## Roadmap

Feature numbers are tentative. Each feature is specified with [Spec Kit](https://github.com/github/spec-kit) in `specs/` before it is built.

| # | Feature | Status |
|---|---|---|
| 001 | Create and fetch disputes | Done |
| 002 | State transitions, safe under concurrent requests | Done |
| 003 | LLM client abstraction (Anthropic and Azure OpenAI adapters, fake for tests) | Planned |
| 004 | Intake: free text to a validated dispute (structured output) | Planned |
| 005 | Evaluation dataset and script (accuracy, latency, cost) | Planned |
| 006 | PostgreSQL persistence with migrations | Planned |
| 007 | RAG with cited sources over dispute policies (pgvector) | Planned |
| 008 | Public deployment (Azure Container Apps, scale to zero) | Planned |
| 009 | Agent (LangGraph) with `get_dispute` and `search_policy` tools | Planned |
| 010 | Read-only MCP server and deployment CI/CD | Planned |
| 011 | Response cache (Redis) and tracing (Langfuse) | Planned |
| 012 | Guardrails (PII, prompt injection) and a multi-model comparison | Planned |

Figures for quality, latency and cost will appear here only once they have been measured.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): components, design decisions, what exists and what is planned.
- [`specs/`](specs/): one folder per feature (spec, plan, tasks, API contract).
- [`.specify/memory/constitution.md`](.specify/memory/constitution.md): the project principles.

## Run it

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), and Docker (for PostgreSQL, used from feature 006 on).

```bash
uv sync
uv run uvicorn disputes.main:app --reload
# http://127.0.0.1:8000/docs
uv run pytest
```

### Concurrency tests

Transitions are tested for races at two levels, and the two prove different things:

- `test_transition_is_atomic_under_a_slow_read` (repository): 8 threads try the same move on one dispute while reads are made slow on purpose. Exactly one succeeds. Without the lock all 8 succeed, so this test is what proves the lock is needed.
- `tests/test_transition_concurrency.py` (HTTP): competing requests are released together by a barrier, 50 rounds per case, and every round must end with a valid state and an unbroken history. The barrier starts the requests together but cannot force the handlers to interleave, so these tests check that no round ends in an invalid result; they pass even without the lock.

Local database (the service does not use it yet; it is ready for the persistence feature):

```bash
cp .env.example .env
docker compose up -d postgres
```

## Relationship to Bank

Independent. This service never modifies Bank. Later it will read transfer state through a documented, read-only interface using synthetic data.
