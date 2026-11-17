---

description: "Task list for LLM Client Abstraction"
---

# Tasks: LLM Client Abstraction

**Input**: Design documents from `/specs/003-llm-client/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/llm-client.md

**Tests**: REQUIRED. Constitution principle I (NON-NEGOTIABLE): in every phase, write the test
first, run it, and confirm it fails for the expected reason (red) before writing the code that
makes it pass (green). Do not combine a test task and its implementation task into one step. When
a test already passes at its red run, record that and why; it then only guards against regressions.

**Organization**: Tasks are grouped by user story. US1 and US2 are P1, US3 and US4 are P2. The
phases are ordered by dependency, not strictly by priority: the failure classes (US3) come before
the fake client (US2) because the fake raises them, and the translation of provider failures into
those classes is tested in the adapter phase (US4) with the `[US3]` label.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 = ask a model through one neutral interface, US2 = test without a network
  (fake), US3 = failures in one vocabulary with a retryable flag, US4 = Anthropic adapter, settings
  and the manual real call
- All paths are relative to the repository root. Commands: `uv run pytest`, `uv run ruff check .`
- **Who writes what** (CLAUDE.md): tasks tagged *(owner)* are core logic (models, errors,
  settings, adapter) that the project owner writes and must be able to explain line by line before
  committing. Tasks tagged *(AI may draft)* are scaffolding, scripts or documentation the assistant
  can generate; the owner still reviews them. Untagged tasks are runs and checks. For tests, the
  owner tries first and the assistant explains and reviews.
- Facts marked *(confirm on install)* in [research.md](research.md) are checked in T005; replace
  those marks with the observed result.
- Not in this feature: retries and backoff, the Azure OpenAI adapter, streaming, tool use,
  structured output, any HTTP endpoint using the client, caching, cost calculation.

## Phase 1: Setup

**Purpose**: Confirm the baseline, branch, add the dependency, check install-time facts

- [ ] T001 On branch `docs/spec-kit-003-llm-client` run `uv sync`, `uv run pytest` and
  `uv run ruff check .`; record the number of passing tests and that lint is clean (no files
  changed). Do not assume the number: read it from the output
- [ ] T002 Commit the spec artifacts (`specs/003-llm-client/`, `.specify/feature.json`) on
  `docs/spec-kit-003-llm-client` as one docs commit (leave the unrelated `CLAUDE.md` edit out
  unless you mean to include it)
- [ ] T003 Create the implementation branch `feat/003-llm-client` from that docs branch
- [ ] T004 Add the dependency with `uv add anthropic`; check that only `pyproject.toml` and
  `uv.lock` changed; record the installed version in `specs/003-llm-client/research.md` section 10
- [ ] T005 [P] Check the *(confirm on install)* facts with throwaway commands in the scratch
  area, not committed: (a) `anthropic.APITimeoutError` is a subclass of
  `anthropic.APIConnectionError`; (b) the attribute that holds retries on `AsyncAnthropic(...,
  max_retries=0)` and on its timeout; (c) `repr(SecretStr("x"))` and `str(...)` are masked;
  (d) the `anyio` pytest plugin is active (`uv run pytest --trace-config` lists it); (e) a module
  in `tests/` is importable by bare name from another test (the `from fake_llm import ...` style);
  (f) `httpx2.MockTransport` works with `AsyncAnthropic(http_client=...)` (the wrapper class the
  SDK expects, for example `DefaultAsyncHttpxClient`); (g) the `request-id` response header is
  exposed on the SDK's status errors. Write each observed result into research.md in place of its
  mark; if (d) or (e) fail, apply the fallback written in research.md sections 8 and 9
- [ ] T006 [P] (AI may draft) Add the three variables to `.env.example` with placeholders only
  (`ANTHROPIC_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS=60`), keeping the existing
  `DATABASE_URL` line. Comment the timeout as "maximum seconds to wait for each phase of a call
  (not a total cap)". The key placeholder must not look like a real key (FR-018). Confirm
  `.env` stays ignored (`git check-ignore .env`) and `.env.example` is not
- [ ] T007 Create the empty package `src/disputes/llm/__init__.py`

---

## Phase 2: Foundational

**Purpose**: Async tests must run before any async test is written for a story

- [ ] T008 (AI may draft) Write a throwaway test `tests/test_llm_async_smoke.py` with one
  `@pytest.mark.anyio` async test that awaits `asyncio.sleep(0)` and asserts true
- [ ] T009 Run it with `uv run pytest tests/test_llm_async_smoke.py` and confirm it fails or
  errors for the expected reason (no `anyio_backend` fixture, so the trio variant is requested and
  trio is not installed). Record the message
- [ ] T010 (AI may draft) Add a session-scoped `anyio_backend` fixture returning `"asyncio"` to
  `tests/conftest.py`
- [ ] T010a (AI may draft) Add an `autouse` fixture to `tests/conftest.py` that replaces
  `socket.socket` with a function raising `RuntimeError("network access in a unit test")`, so any
  accidental real call fails loudly (FR-019, SC-003). The FastAPI `TestClient` uses an in-memory
  transport, but confirm by running the existing suite with the fixture active; if a 001/002 test
  breaks, limit the fixture to modules named `test_llm_*`
- [ ] T011 Run the smoke test again and confirm green, then delete
  `tests/test_llm_async_smoke.py` (the real async tests below cover it). If the anyio plugin
  cannot be made to work, use the fallback in research.md section 9 (`asyncio.run` inside sync
  tests) and say so in the commit

**Checkpoint**: async tests run; US1 can start.

---

## Phase 3: User Story 1 - Ask a model through one provider-neutral interface (Priority: P1)

**Goal**: Immutable validated request/response types and the `LLMClient` Protocol.

**Independent Test**: Build requests and responses, see invalid ones rejected, see responses
frozen, and see a class with the right method count as an `LLMClient`.

- [ ] T012 [P] [US1] Write `tests/test_llm_models.py` (sync) covering, from
  [data-model.md](data-model.md): `Message` accepts roles `user` and `assistant` and rejects any
  other role (FR-003); `Message.content` "not empty after trimming whitespace": `""`, `"   "` and
  `"\n"` rejected, and valid text is stored untrimmed; `LLMRequest.messages` "at least one message"
  (empty list rejected), `max_tokens` "greater than zero" (0 and -1 rejected, 1 accepted) (FR-004);
  `system` optional with default `None`, and `""` or `"  "` rejected (FR-004); unknown fields rejected, with
  one parametrized case each for `temperature`, `top_p`, `top_k` (FR-005); a list passed as
  `messages` becomes a tuple and the caller's list is unchanged (FR-008); assigning to a field of
  `Message`, `LLMRequest`, `TokenUsage` or `LLMResponse` raises (FR-006); `TokenUsage` tokens
  "greater than or equal to zero" (-1 rejected, 0 accepted); `LLMResponse.model` "not empty";
  `LLMResponse.text` may be `""`; `StopReason` has exactly `completed`, `max_tokens`, `other`
- [ ] T013 [P] [US1] Write `tests/test_llm_client_protocol.py` (sync): a tiny class with an
  `async def complete(self, request)` is an instance of `LLMClient` (runtime-checkable
  Protocol); a class without `complete` is not
- [ ] T014 [US1] Run both files and confirm red (import errors for the missing package modules).
  Record the reason
- [ ] T015 [US1] (owner) Implement `src/disputes/llm/models.py`: `Role`, `Message`, `LLMRequest`,
  `StopReason`, `TokenUsage`, `LLMResponse`, all frozen with `extra="forbid"`, exactly as in
  data-model.md (no sampling fields; `messages` is a `tuple[Message, ...]`)
- [ ] T016 [US1] (owner) Implement `src/disputes/llm/client.py`: the `@runtime_checkable`
  `LLMClient` Protocol with `async def complete(self, request: LLMRequest) -> LLMResponse`
- [ ] T017 [US1] Run `uv run pytest tests/test_llm_models.py tests/test_llm_client_protocol.py`
  and `uv run ruff check .`; confirm green and clean. Be ready to explain why the models are frozen
  and why `messages` is a tuple

**Checkpoint**: US1 complete and independently testable.

---

## Phase 4: User Story 3 - Failures in one vocabulary, ready for retries (Priority: P2)

**Goal**: The service's own exception family with a `retryable` flag. (Translating provider
failures into it is tested in Phase 6 with the `[US3]` label.)

**Independent Test**: Each exception is an `LLMError`, and its `retryable` flag has the intended
value without creating an instance.

- [ ] T018 [US3] Write `tests/test_llm_errors.py` (sync): the five subclasses are subclasses of
  `LLMError`; `retryable` read on the class (no instance) is `True` for `LLMRateLimitError`,
  `LLMTimeoutError`, `LLMProviderUnavailableError` and `False` for `LLMAuthenticationError`,
  `LLMBadRequestError` and the base `LLMError` (FR-010); `status_code` and `request_id` default to
  `None` and can be set through the constructor; `str(exc)` is the message given;
  `LLMConfigurationError` is **not** a subclass of `LLMError`; `catch LLMError` does not catch it
- [ ] T019 [US3] Run it and confirm red (module missing). Record the reason
- [ ] T020 [US3] (owner) Implement `src/disputes/llm/errors.py` with the hierarchy in
  data-model.md: `retryable` as a class attribute, optional `status_code` and `request_id`
  attributes, and a separate `LLMConfigurationError`
- [ ] T021 [US3] Run `uv run pytest tests/test_llm_errors.py` and `uv run ruff check .`; confirm
  green and clean

**Checkpoint**: US3 vocabulary ready; the fake and the adapter can use it.

---

## Phase 5: User Story 2 - Test code that uses the client without a network (Priority: P1)

**Goal**: `FakeLLMClient` in `tests/` with scripted answers, recorded calls and simulated
failures.

**Independent Test**: Script two answers and one failure, make three calls, and check order,
the raised failure and the recorded requests.

- [ ] T022 [US2] Write `tests/test_llm_fake.py` (async, `@pytest.mark.anyio`), importing
  `from fake_llm import FakeLLMClient, FakeScriptExhaustedError`: scripted responses come back in
  order; every request is recorded in `calls`, in order, equal to what was sent; a scripted
  failure of each of the six kinds (authentication, bad request, rate limit, timeout, provider
  unavailable, base) is raised as that exact class (FR-011); a response then a failure then a
  response works in sequence; an empty script raises `FakeScriptExhaustedError`, which is not an
  `LLMError`; the fake is an `LLMClient`; the request's messages are unchanged after the call;
  the `fake_llm` fixture gives a fresh instance per test; no network: monkeypatch
  `socket.socket` to raise, use the fake, and assert nothing raised (FR-019)
- [ ] T023 [US2] Run it and confirm red (`fake_llm` missing). Record the reason
- [ ] T024 [US2] (AI may draft) Implement `tests/fake_llm.py`: `FakeLLMClient` with a queue,
  `will_return(response)`, `will_fail(error)`, `calls`, `complete`, plus
  `FakeScriptExhaustedError` (see research.md section 8). Keep it small enough to read in one
  sitting
- [ ] T025 [US2] (AI may draft) Add the `fake_llm` fixture to `tests/conftest.py`, returning a
  new `FakeLLMClient()`
- [ ] T026 [US2] Run `uv run pytest tests/test_llm_fake.py` and `uv run ruff check .`; confirm
  green and clean

**Checkpoint**: US1, US3 and US2 work with no key and no network.

---

## Phase 6: User Story 4 - Anthropic adapter, settings and the manual real call (Priority: P2)

**Goal**: Settings read from the environment, the adapter with retries off, failure translation,
and one documented real call.

**Independent Test**: With the real SDK against a mock HTTP transport: success maps to the
neutral response, every failure kind maps to the right exception after exactly one request, and
the key never appears. Separately, one manual real call.

### Settings

- [ ] T027 [US4] Write `tests/test_llm_settings.py` (sync; use `monkeypatch` and pass
  `env_file=None` so a developer's `.env` is ignored): values load from the environment;
  `repr` and `str` of the settings do not contain the key sentinel `sk-test-SENTINEL` (FR-016);
  `llm_timeout_seconds` defaults to 60; a missing key raises `LLMConfigurationError` whose message
  contains `ANTHROPIC_API_KEY`; a missing or empty model names `LLM_MODEL`; a timeout of `0`,
  `-5` or `abc` names `LLM_TIMEOUT_SECONDS` ("greater than zero"); in no case does the message
  contain a supplied raw value; running `python -c "import disputes.llm.anthropic_adapter"` in a
  subprocess (started with `sys.executable`, `cwd` at the repository root and `PYTHONPATH=src`,
  because the subprocess does not inherit pytest's `pythonpath`) with `ANTHROPIC_API_KEY`
  removed from its environment exits 0 (FR-017; this one
  fails until T035, so mark it as expected red and run it again then)
- [ ] T028 [US4] Run it and confirm red (module missing). Record the reason
- [ ] T029 [US4] (owner) Implement `src/disputes/llm/settings.py`: `LLMSettings(BaseSettings)`
  with the three fields and env names from data-model.md, ignoring unknown variables, and a
  `load_settings(env_file=...)` function that builds it on demand (never at import) and converts a
  validation error into `LLMConfigurationError` naming the variable, built from the field name and
  never from the raw input
- [ ] T030 [US4] Run `uv run pytest tests/test_llm_settings.py` (all but the subprocess import
  test should pass) and `uv run ruff check .`

### Adapter

- [ ] T031 [US4] Write the success-path tests in `tests/test_llm_anthropic_adapter.py` (async,
  real SDK, `httpx2.MockTransport` through `http_client`, sentinel key, a helper that builds the
  adapter and records requests): a normal answer maps text, `usage` input/output tokens, `model`
  taken from the answer (not from the configured name) and `stop_reason` (FR-006, FR-012); the
  request body sent has the model, `max_tokens`, the system prompt when given, the messages, and
  none of `temperature`, `top_p`, `top_k`; no `system` key when it is `None`; text blocks are
  concatenated and a `thinking` block before the text is ignored (research section 3); empty
  `content` gives `text == ""`; stop reason mapping: `end_turn` and `stop_sequence` to `completed`,
  `max_tokens` to `max_tokens`, and `tool_use`, `pause_turn`, `refusal` to `other` (clarification
  1); the adapter is an `LLMClient`; the messages passed in are unchanged; two concurrent calls
  (`asyncio.gather`) each get their own answer (FR-008); SC-008: one caller function
  `async def ask(client: LLMClient) -> str` returns the same text when given the fake and when
  given the adapter, with no change to the function
- [ ] T032 [US4] [US3] In the same file add the failure-translation tests: for each row of the
  table in research.md section 4 parametrize the HTTP status (401, 403 to authentication; 400, 404,
  422 to bad request; 429 to rate limit; 500, 502, 503, 529 to provider unavailable; 418 to the
  base `LLMError`), HTTP 408 and a `httpx2.ReadTimeout` raised by the transport to
  `LLMTimeoutError`, 409 to the base `LLMError` (not retryable), and a `httpx2.ConnectError` to
  `LLMProviderUnavailableError`; for each assert the exact class, the
  `retryable` value, `status_code`, `request_id` from the `request-id` header when present, and
  that `__cause__` is `None` (raised `from None`, research section 4)
- [ ] T033 [US4] In the same file add the retries-off and key-safety tests: for the 500, 429 and
  timeout cases the transport handler was called exactly once (SC-005, FR-013); the SDK client's
  retries attribute (the one found in T005, read through the adapter's `_client` attribute) is `0`
  and its timeout equals the configured seconds
  (FR-015); for every failure kind, the sentinel key is not in `str(exc)`, `repr(exc)`, the
  formatted traceback (`traceback.format_exception`), `repr(adapter)`, `str(adapter)` or captured
  log records at DEBUG level (FR-016); `from_env()` with all variables set builds the adapter and
  with `ANTHROPIC_API_KEY` missing raises `LLMConfigurationError` naming it (FR-017)
- [ ] T034 [US4] Run the file and confirm red (module missing), then record the reason
- [ ] T035 [US4] (owner) Implement `src/disputes/llm/anthropic_adapter.py`: `AnthropicLLMClient`
  built from `api_key: SecretStr`, `model`, `timeout_seconds` and an optional `http_client`
  (tests only); it creates `AsyncAnthropic(api_key=<secret value, read once>, max_retries=0,
  timeout=...)` and keeps it in the attribute `self._client` (tests read it); `from_env()` uses `load_settings()`; `complete` calls the SDK once, reads only
  `text` blocks, maps usage, model and stop reason, and translates failures per research.md
  section 4 (timeout class tested before connection class) with our own message, status code and
  request id, raised `from None`; give the class a `__repr__` that shows no key
- [ ] T036 [US4] Run `uv run pytest tests/test_llm_anthropic_adapter.py
  tests/test_llm_settings.py` (now including the subprocess import test) and
  `uv run ruff check .`; confirm green and clean. If a test fails because a detail of the SDK
  differs from research.md, fix research.md with the observed fact, not just the code

### Manual real call

- [ ] T037 [US4] (AI may draft) Write `scripts/manual_anthropic_call.py` (outside `tests/`, so
  pytest never collects it): refuses to run if the `CI` environment variable is set; builds the
  adapter with `from_env()`; sends one short synthetic prompt with a small `max_tokens`; prints
  text, input and output tokens, model and stop reason; on `LLMError` prints the class name,
  `retryable`, `status_code` and `request_id`, never the key. Confirm `uv run pytest` does not
  collect it
- [ ] T038 [US4] Run the script once with your own key (quickstart section 4). Do not paste the
  key anywhere. Note the date, and the real output
- [ ] T039 [US4] Create `docs/evidence/llm-client-anthropic.md` with the date, the exact command,
  the prompt and the real output of T038 (text, tokens, model, stop reason). State plainly that it
  is one manual call, not run in CI, and that the timeout default of 60 s is not validated by it
  (research.md section 6); if the call timed out or failed, record that as it happened
- [ ] T040 [US4] Check the evidence file and the whole repository for secrets: search for
  `sk-ant`, `ANTHROPIC_API_KEY=` followed by a value, and the test sentinel outside `tests/`; fix
  anything found before committing

**Checkpoint**: all four stories work; one real call is documented.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T041 (owner) Fill `src/disputes/llm/__init__.py` with re-exports of the interface, models,
  errors and settings, but **not** the adapter (importing the package must not load the SDK).
  Add a one-line test in `tests/test_llm_models.py` that `from disputes.llm import LLMClient,
  LLMRequest, LLMResponse, LLMError` works
- [ ] T042 (AI may draft) Update `README.md`: the Roadmap row for feature 003 and a short "LLM
  client" section stating only what exists and is tested (interface, fake in `tests/`, Anthropic
  adapter, environment variables, how to run the manual call) with retries, Azure adapter and
  any endpoint labelled planned. Constitution VI
- [ ] T043 (AI may draft) Update `docs/ARCHITECTURE.md` with the `disputes.llm` package: the
  interface, the one-SDK-import rule, the failure table and the "no hidden retries" decision
- [ ] T044 Run the full suite and lint: `uv run pytest` and `uv run ruff check .`; record the
  passing count (compare with T001) and that no test needed a key or the network (the socket
  guard from T010a enforces it; also run once with `ANTHROPIC_API_KEY` unset)
- [ ] T045 Check SC-001 (deterministic over 100 runs): run
  `for i in $(seq 1 100); do uv run pytest -q tests/test_llm_fake.py || break; done` and record that
  all passed; check SC-002 to SC-008 against the tests and record where each is covered
  (tracing table in the PR description)
- [ ] T046 Walk through [quickstart.md](quickstart.md) sections 1 to 3 as written and note any
  step that does not work as described; fix the document
- [ ] T047 Update `CLAUDE.md` per "Al cerrar una feature": "Estado actual", the roadmap row 003
  (the Azure OpenAI adapter in the description stays pending), and move to "Decisiones ya
  tomadas" what was confirmed (the `LLMClient` shape, `retryable` flag, `max_retries=0`, key as
  `SecretStr`, fake in `tests/`, configuration error not an `LLMError`). Keep the file's language
  convention
- [ ] T048 Open the PR from `feat/003-llm-client` into `develop`; wait for CI green (tests,
  lint, and the existing image job, which must still start the container with no key set); fix
  anything red; merge only when green

---

## Dependencies & Execution Order

- Phase 1 then Phase 2 (async support) then user stories in the order shown: US1, US3, US2, US4.
- US1 needs only Phase 1 and 2. US3 needs nothing from US1 but is placed after it. US2 needs US1
  (models) and US3 (errors). US4 needs US1, US3 and, for its tests, the async support; it does
  not need US2.
- Inside each story: tests, run red, implementation, run green. Tests for the adapter (T031 to
  T033) share one file, so they are sequential.
- Polish needs all stories.

### Parallel opportunities

- T005 and T006 can run together (different files, no shared state).
- T012 and T013 are separate files and can be written together.
- After T017, US3 (T018 to T021) can run in parallel with writing the settings tests (T027) since
  they touch different files, but the owner works one topic at a time (CLAUDE.md), so this is
  allowed, not recommended.

## Implementation Strategy

- **MVP**: Phases 1 and 2, then US1 (T012 to T017). That gives the neutral types and the
  interface; everything else builds on it.
- **Incremental**: add US3 and US2 next (errors and the fake), which unlocks testing of any later
  feature without a network. Add US4 last, because it is the only part that touches the provider
  SDK and the only part that needs a key (and only for the manual call).
- **Stop point**: if time is short, US1 + US3 + US2 deliver the contract and the test double; the
  adapter (US4) is the remaining piece and does not change them.

## Notes

- Owner writes: T015, T016, T020, T029, T035, T041. Everything else is scaffolding, runs or
  docs the assistant may draft.
- Commit after each green checkpoint, with the test and its implementation in the same
  or adjacent commits as the repository's earlier features did.
