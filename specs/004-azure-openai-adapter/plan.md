# Implementation Plan: Azure OpenAI Adapter for the LLM Client

**Branch**: `feat/004-azure-openai-adapter` (not yet created) | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-azure-openai-adapter/spec.md`

## Summary

Add a second `LLMClient` implementation, `AzureOpenAILLMClient`, in one new module
(`src/disputes/llm/azure_openai_adapter.py`). It mirrors the Anthropic adapter: one attempt per
call (`max_retries=0`), provider errors translated by exception class into the existing error
family with service-written messages raised outside the `except` block, key held as `SecretStr`.
It talks to the Azure v1 endpoint with the SDK's `AsyncOpenAI` class (the same class and
`base_url` style the manual call used), sends `max_completion_tokens`, names the deployment as
`model`, and maps `finish_reason` to the neutral stop reason. An answer with no text raises the
base `LLMError` (clarified in the spec). Settings are three new variables plus the existing
`LLM_TIMEOUT_SECONDS`. A shared behavior suite runs against the fake, the Anthropic adapter and
the Azure adapter; the Anthropic adapter and the 001-003 tests are not touched.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, Pydantic v2, pydantic-settings, `anthropic` (existing), **`openai>=3.55`** (new, see Dependency justification). `openai` 3.55.1 depends on `httpx2`, the same HTTP library the Anthropic SDK and the existing tests already use.

**Storage**: N/A

**Testing**: pytest with `anyio`; the real SDK runs against `httpx2.MockTransport` (no network), as in `tests/test_llm_anthropic_adapter.py`. The autouse network guard in `tests/conftest.py` stays on.

**Target Platform**: Linux container (CI) and Windows dev machine

**Project Type**: Single Python web-service project (library code under `src/disputes/llm/`)

**Performance Goals**: None. Latency is explicitly not measured by this feature.

**Constraints**: One attempt per call; no key in any error, repr, log or traceback; SDK imported only in the adapter module; the tests of features 001-003 are not modified.

**Scale/Scope**: One new source module, one settings class, one shared test file, one Azure-specific test file, one script, one evidence document.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Tests first, focused | Pass | 10 test functions (5-10 per feature, owner-explainable); red then green; no tests of what Pydantic or the SDK already guarantee. See "Test plan". |
| II. Valid state transitions | N/A | No dispute state is touched. |
| III. Synthetic data only | Pass | Test keys are sentinels; `.env.example` has placeholders; the evidence uses a generic question. |
| IV. Validate at the boundary | Pass | Settings are validated by Pydantic; the request type is the existing validated `LLMRequest`. No endpoint added. |
| V. Independent service | Pass | Bank is not involved. |
| VI. Honest documentation | Pass | Evidence states its limits; README/CLAUDE.md claim only what is tested; unverified provider facts are labeled (see research.md). |
| Technical Constraints: new core dependency | Pass, with justification | See below. |

### Dependency justification (Technical Constraints)

`openai` is the official SDK for the chat completions API that Azure exposes at its v1 endpoint.
Alternative: calling the REST endpoint by hand with `httpx2`. Rejected: the SDK already gives
the error classes, timeout handling and typed response that the adapter maps from, and
`max_retries=0` is a documented constructor argument; re-implementing them adds code the owner
would have to maintain and explain. The cost is one more dependency, imported in exactly one
module (FR-016), and it shares `httpx2` with `anthropic`. No constitution amendment needed.

## Project Structure

### Documentation (this feature)

```text
specs/004-azure-openai-adapter/
├── plan.md              # This file
├── research.md          # Phase 0: decisions and what is verified vs not
├── data-model.md        # Phase 1: settings, mapping tables
├── quickstart.md        # Phase 1: how to validate
├── contracts/
│   └── azure-adapter-contract.md   # Phase 1: outgoing request, mappings, errors, settings
├── checklists/requirements.md
└── tasks.md             # Created by /speckit-tasks
```

### Source Code (repository root)

```text
src/disputes/llm/
├── azure_openai_adapter.py   # NEW: AzureOpenAILLMClient (only module importing `openai`)
├── settings.py               # CHANGED: add AzureOpenAISettings + load_azure_settings (load_settings unchanged in behavior)
├── anthropic_adapter.py      # unchanged
├── client.py / models.py / errors.py   # unchanged

tests/
├── llm_harness.py            # NEW: per-implementation helper (fake / anthropic / azure) used by the shared suite
├── test_llm_contract.py      # NEW: shared behavior suite, parameterized over the 3 implementations
├── test_llm_azure_adapter.py # NEW: Azure-specific behavior
└── (all existing files unchanged)

scripts/manual_azure_openai_call.py        # NEW: manual real call (replaces the untracked scratch first_azure_call.py)
docs/evidence/llm-client-azure-openai.md   # NEW: the recorded real call and its limits
.env.example                        # CHANGED: Azure variables, placeholders only
pyproject.toml / uv.lock            # CHANGED: add openai
```

**Structure Decision**: Same layout as feature 003: one adapter module per provider next to the
interface; the adapter is the only place that imports its SDK. Settings stay in `settings.py`
with a second class, because the Anthropic `LLMSettings` requires `ANTHROPIC_API_KEY` and
`LLM_MODEL`, which an Azure user must not need.

## Test plan (Principle I)

10 test functions, red before green. Shared cases multiply by 3 implementations and the
parameterized ones by their parameters, so pytest reports more cases than functions; each
function stays short and readable.

Shared (`test_llm_contract.py`, 4 functions, run for fake, Anthropic, Azure):
1. An answer comes back as the neutral response (text, usage, answering model, completed); the client is an `LLMClient`.
2. An answer cut by the token limit is returned, not raised (stop reason max tokens).
3. The request is not modified by a call, and two concurrent calls get their own answers.
4. Each failure kind (authentication, bad request, rate limit, timeout, provider unavailable, other) raises the matching service error with the right `retryable` flag (parameterized over 6 kinds).

Azure-specific (`test_llm_azure_adapter.py`, 6 functions):
5. The outgoing request carries `max_completion_tokens` and not `max_tokens`, the deployment as `model`, the system prompt, no sampling parameters, and the bearer key (FR-005, FR-006, FR-018).
6. Provider `finish_reason` mapping: `stop` to completed, `length` to max tokens, others to other (parameterized).
7. No text (empty choices; null content; content-filter finish) or no `usage` raises the base `LLMError` with a service message (FR-010).
8. One attempt per failure (500, 429, timeout, connection) and the SDK client has retries off and the configured timeout (FR-011, FR-014).
9. The key is in no error text, traceback, repr or log, and neither `__cause__` nor `__context__` holds the provider error (FR-009).
10. Settings (parameterized, 4 cases): each of the three variables missing in turn, and an invalid base URL, raise `LLMConfigurationError` naming the variable and never containing the supplied value (FR-013). That the module imports without any `AZURE_*` variable is shown by the test file itself (it imports the module at collection time in an environment without them, as in CI); the success path of `from_env` is exercised by the manual real call and quickstart section 3 (FR-012).

Existing Anthropic tests stay as they are and keep running; the shared suite adds Anthropic
coverage of the contract, it does not replace theirs. Low-risk cases kept as a list, not tests:
HTTP 408/409/418 mapping variants, a very long deployment name,
trailing slash in the base URL.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| New `openai` dependency | Typed client, error classes, timeouts | Hand-written REST calls would duplicate the SDK (see justification) |
| `tests/llm_harness.py` | One suite over three implementations needs a per-implementation way to script an answer or a failure | Copying the tests per provider is what the spec's User Story 2 forbids |

## Open items carried into implementation

- The system prompt is sent as a `system` role message. Newer reasoning models prefer `developer`; whether the gpt-5.4-mini deployment accepts `system` is **not verified** and is checked by the manual call (US5). If rejected, switch the role and record it in the evidence.
- Variable names for the manual script follow the scratch script: `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`.
- Roadmap numbering: this directory is `004` but `CLAUDE.md` reserves 004 for intake. Reconcile when closing the feature.
