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

### LLM client (internal; no endpoint uses it yet)

A provider-neutral way to ask a language model, in `src/disputes/llm/`. It is a Python interface for later features, not an HTTP feature.

- **Interface**: `LLMClient.complete(request)`, async. A request has an optional system prompt, a non-empty list of messages (role `user` or `assistant`, text not empty) and `max_tokens`. There are no sampling parameters (`temperature`, `top_p`, `top_k`): they are rejected, because current Claude models reject them. The response is immutable: text, token usage, the model that answered and a neutral stop reason (`completed`, `max_tokens`, `other`). A cut-off answer is returned, not raised.
- **Failures**: provider errors become the service's own `LLMError` family (authentication, bad request, rate limit, timeout, provider unavailable, and a base error), each with a `retryable` flag. Nothing retries yet: **the adapter makes one attempt per call**, with the SDK's own automatic retries turned off.
- **Anthropic adapter**: `AnthropicLLMClient`, built from the environment. The API key is a secret value that is never printed, logged or put in an error message; a missing key fails with an error naming `ANTHROPIC_API_KEY` when the adapter is built, not when the module is imported.
- **Azure OpenAI adapter**: `AzureOpenAILLMClient`, built from `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_DEPLOYMENT`. It calls a chat model deployed in Microsoft Foundry (Azure OpenAI) and returns the same neutral response. It sends the maximum output tokens as `max_completion_tokens` (the service rejects `max_tokens`), names the deployment as the model, and maps `finish_reason` (`stop` to `completed`, `length` to `max_tokens`, anything else to `other`). Same rules as the Anthropic adapter: one attempt per call, the key is never printed or put in an error. Unlike the Anthropic adapter, an answer with no text (for example blocked by the content filter) or with no token usage raises the base `LLMError` instead of returning empty text; the two behave differently in that one case for now.
- **Fake for tests**: `FakeLLMClient` (in `tests/`) returns scripted answers and failures and records the requests. Unit tests never call a real model: a guard in `tests/conftest.py` makes any real network connection fail the test, and the adapter is tested with the real SDK against an in-memory HTTP transport.
- **Shared behavior tests**: one suite (`tests/test_llm_contract.py`) runs the same checks against the fake, the Anthropic adapter and the Azure OpenAI adapter, with no network.
- **Evidence of real calls**: one call per provider was made by hand and is recorded in [`docs/evidence/llm-client-anthropic.md`](docs/evidence/llm-client-anthropic.md) and [`docs/evidence/llm-client-azure-openai.md`](docs/evidence/llm-client-azure-openai.md), including what they do not show (latency, cost, most failure kinds). They are not run in CI.

**Current limits:**
- Disputes are stored **in memory**: they are lost on restart, and with several worker processes each process has its own copy.
- A transition is atomic (a lock inside the in-memory repository) only within one process. With several worker processes each has its own memory and its own lock; PostgreSQL (feature 006) is what removes that limit.
- No authentication, and the referenced transaction is not checked to exist.
- The LLM client exists (see below) but **no endpoint uses it yet**: there is no AI behavior in the API today.

## Roadmap

Feature numbers are tentative. Each feature is specified with [Spec Kit](https://github.com/github/spec-kit) in `specs/` before it is built.

| # | Feature | Status |
|---|---|---|
| 001 | Create and fetch disputes | Done |
| 002 | State transitions, safe under concurrent requests | Done |
| 003 | LLM client abstraction: interface, fake for tests, Anthropic adapter | Done |
| — | Azure OpenAI adapter for the same interface (spec `004-azure-openai-adapter`) | Done |
| 004 | Intake: free text to a validated dispute (structured output; its Spec Kit directory will be numbered 005, since 004 went to the Azure adapter) | Planned |
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

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), and Docker (to build the image, and for PostgreSQL, used from feature 006 on).

```bash
uv sync
uv run uvicorn disputes.main:app --reload
# http://127.0.0.1:8000/docs
uv run pytest
```

### Docker image

```bash
docker build --tag disputes-ai-copilot .
docker run --rm --publish 8000:8000 disputes-ai-copilot
# http://127.0.0.1:8000/docs
```

The image is built in two stages (dependencies installed from `uv.lock` with `uv sync --locked`; the final stage holds only the virtual environment, with no uv, sources or dev tools), runs as a non-root user and has a health check on `GET /health`. It starts **one** uvicorn process on purpose: storage is in memory, so extra workers would each have their own data and their own lock.

CI builds the image on every push and pull request, checks that the container does not run as root and that `GET /health` answers. The image is not pushed to any registry yet (public deployment is feature 008).

### Concurrency tests

Transitions are tested for races at two levels, and the two prove different things:

- `test_transition_is_atomic_under_a_slow_read` (repository): 8 threads try the same move on one dispute while reads are made slow on purpose. Exactly one succeeds. Without the lock all 8 succeed, so this test is what proves the lock is needed.
- `tests/test_transition_concurrency.py` (HTTP): competing requests are released together by a barrier, 50 rounds per case, and every round must end with a valid state and an unbroken history. The barrier starts the requests together but cannot force the handlers to interleave, so these tests check that no round ends in an invalid result; they pass even without the lock.

### LLM client configuration

Only needed to build an adapter (no endpoint does yet) and to run the manual calls. Copy `.env.example` to `.env` (ignored by git) and fill in:

| Variable | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | your own key; never commit it |
| `LLM_MODEL` | yes | the model identifier to send; there is no default |
| `LLM_TIMEOUT_SECONDS` | no | default 60: the maximum wait for each phase of a call, not a total cap; shared by both adapters |
| `AZURE_OPENAI_BASE_URL` | yes, for Azure | the v1 endpoint of your resource, ending in `/openai/v1/` |
| `AZURE_OPENAI_API_KEY` | yes, for Azure | your own key; never commit it |
| `AZURE_OPENAI_DEPLOYMENT` | yes, for Azure | the deployment name, not the model id; `LLM_MODEL` is not used by this adapter |

```bash
uv run python scripts/manual_anthropic_call.py     # one real call, manual only; costs a small amount
uv run python scripts/manual_azure_openai_call.py  # the same for Azure OpenAI
```

Local database (the service does not use it yet; it is ready for the persistence feature):

```bash
cp .env.example .env
docker compose up -d postgres
```

## Relationship to Bank

Independent. This service never modifies Bank. Later it will read transfer state through a documented, read-only interface using synthetic data.
