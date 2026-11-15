# Architecture

> Status labels: **Exists** = implemented and tested today. **Planned** = decided or intended, not built yet.
> Feature numbers in this document are tentative; Spec Kit assigns the real ones when each feature is specified.

## 1. Purpose

`disputes-ai-copilot` is a FastAPI service for transaction disputes (a customer contests a charge). It is the AI-facing half of a two-part portfolio system:

- **Bank** (separate repository, .NET, event-driven) is the system being operated: transfers, a saga, idempotent handlers, dead-letter queues.
- **Disputes** (this repository) is the copilot that helps operate it: it turns free-text complaints into valid disputes, answers policy questions with cited sources, and reads the state of transfers.

The two are independent. This service never modifies Bank or its database (constitution, principle V). All data is synthetic.

## 2. Component view

```mermaid
flowchart LR
    client([Client / recruiter])
    subgraph disputes["disputes-ai-copilot"]
        api["FastAPI app<br/>routes, error handlers<br/>(Exists)"]
        domain["Models + state rules<br/>(Exists: models;<br/>Planned: transitions)"]
        repo["DisputeRepository<br/>(Protocol)<br/>(Exists: in-memory;<br/>Planned: PostgreSQL)"]
        llm["LLMClient<br/>(Planned)"]
        rag["Retriever + pgvector<br/>(Planned)"]
        agent["LangGraph agent<br/>(Planned)"]
        mcp["MCP server, read-only<br/>(Planned)"]
        obs["Langfuse, Redis cache<br/>(Planned)"]
    end
    bank[("Bank<br/>(.NET, events)<br/>read-only, synthetic data")]
    providers(["Anthropic API / Azure OpenAI<br/>(Planned)"])

    client --> api
    api --> domain
    domain --> repo
    api -.-> llm
    api -.-> agent
    agent -.-> llm
    agent -.-> rag
    agent -.-> mcp
    llm -.-> providers
    mcp -.-> bank
    api -.-> obs
```

Solid lines exist today; dashed lines are planned.

## 3. What exists today

| Piece | File | Notes |
|---|---|---|
| App wiring | `src/disputes/main.py` | Creates the app, registers error handlers and the router, exposes `GET /health` |
| Routes | `src/disputes/routes.py` | `POST /disputes`, `GET /disputes/{id}`; the repository is provided through a FastAPI dependency |
| Models | `src/disputes/models.py` | `DisputeCreate` (client input) and `Dispute` (stored record) |
| Repository | `src/disputes/repository.py` | `DisputeRepository` Protocol plus an in-memory implementation |
| Errors | `src/disputes/errors.py` | One error envelope for validation errors, not-found and framework HTTP errors |
| Contract | `specs/001-create-and-get-dispute/contracts/` | OpenAPI contract, checked by a test |

Request flow today: the request is validated by Pydantic at the boundary, the route builds a `Dispute` with system-assigned fields (`id`, `state`, `created_at`), and the repository stores it.

### Current limits (stated honestly)

- **Storage is in memory.** Data is lost on restart. With more than one worker process, each process has its own memory, so a dispute created in one worker is not visible from another. This is acceptable only until the PostgreSQL feature.
- **The only state is `open`.** There are no transitions yet.
- **No authentication**, and the referenced transaction is not verified to exist.
- **No AI components yet.**

## 4. Design decisions

| Decision | Why | Status |
|---|---|---|
| `DisputeCreate` (input) separate from `Dispute` (record); input uses `extra="forbid"` | The client may send only what it is allowed to set. Fields such as `state` are assigned by the system, so a client cannot inject them | Exists |
| Repository behind a `Protocol` | Lets PostgreSQL replace the in-memory store without touching the routes | Exists |
| One error format for every error, including those the framework raises (unknown route, wrong method) | Predictable client behavior; covered by tests | Exists |
| Allowed state transitions defined in one place; a closed dispute never reopens | Disputes are a financial process: an invalid or reversible state corrupts the audit trail (constitution II) | Planned |
| Concurrent transitions resolved by an atomic conditional update ("change to X only if the current state is Y"); exactly one wins, the other gets `409 Conflict` | A race on the same dispute must not silently overwrite a final state. In memory this is a lock inside the repository; in PostgreSQL it becomes a conditional `UPDATE` | Planned |
| `LLMClient` interface with two implementations: Anthropic API and Azure OpenAI | Independence from a single provider; cheap development and evals; tests use a fake with no network | Planned |
| Vector search with `pgvector` inside PostgreSQL | One fewer moving part than a separate vector database | Planned |
| The agent is built once, in LangGraph, with read-only tools (`get_dispute`, `search_policy`) | Keeps scope small | Planned |
| MCP server is read-only and reads Bank's transfer state from synthetic data | Bank stays untouched; the interface is documented and replaceable | Planned |
| Public deployment on Azure Container Apps, scale to zero, with a daily cap on model calls | A live link at near-zero cost | Planned |

## 5. Testing approach

Tests come first (red, then green), as the constitution requires. Model calls are never made in unit tests: the `LLMClient` fake returns fixed answers. Quality of model behavior is measured separately with an evaluation dataset and reported in the README with real numbers.

## 6. Where to find more

- `.specify/memory/constitution.md`: the project principles.
- `specs/`: one folder per feature (spec, plan, tasks, contracts).
- `CLAUDE.md`: current state, roadmap and working rules.
