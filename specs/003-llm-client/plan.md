# Implementation Plan: LLM Client Abstraction

**Branch**: `feat/003-llm-client` (specs drafted on `docs/spec-kit-003-llm-client`) | **Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-llm-client/spec.md`

## Summary

Add a new package `src/disputes/llm/` with one async interface, `LLMClient.complete(request)`,
immutable Pydantic types for the request and response (text, token usage, answering model, stop
reason), a family of service exceptions that each declare `retryable`, a scriptable
`FakeLLMClient`, and an `AnthropicLLMClient` adapter built with the SDK's own retries turned off
(`max_retries=0`). Settings (`ANTHROPIC_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`) are read
with Pydantic settings when the adapter is built, never at import; the key is a `SecretStr`. One
real call is made manually and documented. See [research.md](research.md) for the decisions,
[data-model.md](data-model.md) for the types and [contracts/llm-client.md](contracts/llm-client.md)
for the interface.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: Pydantic v2 and `pydantic-settings` (already in `pyproject.toml`); new
runtime dependency `anthropic` (justified in research.md section 10)

**Storage**: N/A

**Testing**: pytest; async tests through the `anyio` plugin already present with Starlette (no
new dev dependency); the real SDK is exercised against an `httpx2` mock transport, never the
network

**Target Platform**: Linux server (Docker), developed on Windows

**Project Type**: web-service (single project); this feature adds a library package, no endpoint

**Performance Goals**: None specified. The only time bound is the configurable call timeout
(default 60 s, a judgment value, not measured)

**Constraints**: Tests first; synthetic data only; no key in the repository, logs, error messages
or `repr`; exactly one provider attempt per call; no network in unit tests

**Scale/Scope**: 1 new package with 5 modules (plus the test double in `tests/`), 1 new runtime dependency, 7 test modules (6 plus the network guard test), 1 manual
script, 1 evidence document, `.env.example` and docs updates

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| I. Tests first | Pass | Tasks will order each test module before its source module. Retries-off and key-safety are proven by tests that can fail (mock transport counts requests; key search over `repr`, messages and settings output) |
| II. Valid state transitions | N/A | No dispute state is touched |
| III. Synthetic data only | Pass | Test and manual prompts are invented text. `.env.example` has placeholders only; `.env` is already ignored. Evidence document is checked for secrets before commit |
| IV. Validate at the boundary | Pass | Request, message, response and settings are Pydantic models validated on construction; there is no HTTP boundary in this feature, and the existing error format is untouched |
| V. Independent service | Pass | No Bank access; the only outside party is the model provider, behind our interface |
| VI. Honest documentation | Pass | The README will say what exists (interface, fake, one adapter) and label retries, Azure adapter and any endpoint as planned. The 60 s timeout is documented as a default, not a measurement. Evidence document holds the real measured output |

**Technical Constraints**: Adding `anthropic` needs a documented justification in the plan. It is
in research.md section 10 (typed errors, no hand-written HTTP, one importing file).

**Post-design re-check**: Pass. The design adds one dependency, no persistence, no endpoint and no
Bank access. One risk is handled by design: leaking the key through a chained provider
exception (raised `from None`, research section 4). The test double lives in `tests/`, so it
never ships in the image.

## Project Structure

### Documentation (this feature)

```text
specs/003-llm-client/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── llm-client.md
├── checklists/
│   └── requirements.md
└── tasks.md              # created by /speckit-tasks
```

### Source Code (repository root)

```text
src/disputes/llm/
├── __init__.py            # re-exports interface, models, errors, settings (not the adapter)
├── models.py              # Role, Message, LLMRequest, StopReason, TokenUsage, LLMResponse
├── errors.py              # LLMError and 5 subclasses, LLMConfigurationError
├── client.py              # LLMClient Protocol
├── settings.py            # LLMSettings (pydantic-settings, SecretStr)
└── anthropic_adapter.py   # AnthropicLLMClient (only file that imports the SDK)

tests/
├── fake_llm.py                  # FakeLLMClient, FakeScriptExhaustedError (test double, not shipped)
├── conftest.py                  # gains the `block_network` guard and the `fake_llm` fixture
├── test_network_guard.py        # proves the guard stops real connections (sync and async)
├── test_llm_models.py
├── test_llm_client_protocol.py
├── test_llm_errors.py
├── test_llm_fake.py
├── test_llm_settings.py
└── test_llm_anthropic_adapter.py

scripts/
└── manual_anthropic_call.py    # manual real call; not collected by pytest, refuses to run in CI

docs/evidence/
└── llm-client-anthropic.md     # filled in after the manual call

.env.example                    # gains the three variables, placeholders only
pyproject.toml                  # gains `anthropic`
```

**Structure Decision**: A sub-package `disputes.llm` keeps the new code apart from the existing
flat modules (`models.py`, `errors.py` already exist for disputes) and avoids name clashes. Tests
stay flat in `tests/` like the existing ones. Only `anthropic_adapter.py` imports the provider
SDK, so the Azure adapter (a later feature) will be a sibling file with no change to the rest.

## Complexity Tracking

No constitution violations. Nothing to justify beyond the dependency noted above.
