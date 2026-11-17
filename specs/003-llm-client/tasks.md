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

- [X] T001 On branch `docs/spec-kit-003-llm-client` run `uv sync`, `uv run pytest` and
  `uv run ruff check .`; record the number of passing tests and that lint is clean (no files
  changed). Do not assume the number: read it from the output.
  **Result (2026-11-17, run on `feat/003-llm-client`, same code as `develop`): 243 passed in
  12.68 s; `ruff check .` clean; working tree unchanged.**
- [X] T002 Commit the spec artifacts (`specs/003-llm-client/`, `.specify/feature.json`) on
  `docs/spec-kit-003-llm-client` as one docs commit (leave the unrelated `CLAUDE.md` edit out
  unless you mean to include it)
- [X] T003 Create the implementation branch `feat/003-llm-client` from that docs branch
  (done after merging the docs PR #5 into `develop`, so the branch starts from the updated
  `develop`)
- [X] T004 Add the dependency with `uv add anthropic`; check that only `pyproject.toml` and
  `uv.lock` changed; record the installed version in `specs/003-llm-client/research.md` section 10
  **Result: `anthropic 2.10.0` (`anthropic>=2.10.0` in `pyproject.toml`); only `pyproject.toml`
  and `uv.lock` changed; recorded in research.md section 10.**
- [X] T005 [P] Check the *(confirm on install)* facts with throwaway commands in the scratch
  area, not committed: (a) `anthropic.APITimeoutError` is a subclass of
  `anthropic.APIConnectionError`; (b) the attribute that holds retries on `AsyncAnthropic(...,
  max_retries=0)` and on its timeout; (c) `repr(SecretStr("x"))` and `str(...)` are masked;
  (d) the `anyio` pytest plugin is active (`uv run pytest --trace-config` lists it); (e) a module
  in `tests/` is importable by bare name from another test (the `from fake_llm import ...` style);
  (f) `httpx2.MockTransport` works with `AsyncAnthropic(http_client=...)` (the wrapper class the
  SDK expects, for example `DefaultAsyncHttpxClient`); (g) the `request-id` response header is
  exposed on the SDK's status errors. Write each observed result into research.md in place of its
  mark; if (d) or (e) fail, apply the fallback written in research.md sections 8 and 9
  **Result (2026-11-17, `anthropic 2.10.0`)**: (a) `APITimeoutError` is a subclass of
  `APIConnectionError`: yes. (b) `client.max_retries` and `client.timeout` hold the given values
  (`0`, `5.0`). (c) `SecretStr` masks `repr` and `str`. (d) `anyio` registered under `pytest11`.
  (e) a module in `tests/` imports by bare name: yes. (f) `DefaultAsyncHttpxClient(transport=
  httpx2.MockTransport(...))` works; `max_retries=0` gave 1 request, `max_retries=2` gave 3.
  (g) `e.request_id` exists and equals the `request-id` header. Extra: the SDK has its own
  `RequestTimeoutError` (408), `ConflictError` (409) and `OverloadedError` (529, subclass of
  `InternalServerError`); a float timeout reaches httpx as connect/read/write/pool. Details in
  research.md; the section 4 table was updated to translate by class.
- [X] T006 [P] (AI may draft) Add the three variables to `.env.example` with placeholders only
  (`ANTHROPIC_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS=60`), keeping the existing
  `DATABASE_URL` line. Comment the timeout as "maximum seconds to wait for each phase of a call
  (not a total cap)". The key placeholder must not look like a real key (FR-018). Confirm
  `.env` stays ignored (`git check-ignore .env`) and `.env.example` is not
  ignored. **Result: `.env` is ignored (`.gitignore` line 12), `.env.example` is not; three variables
  added with placeholders.**
- [X] T007 Create the empty package `src/disputes/llm/__init__.py`
  **Result: created (empty file); `import disputes.llm` works and ruff is clean.**

---

## Phase 2: Foundational

**Purpose**: Async tests must run before any async test is written for a story

- [X] T008 (AI may draft) Write a throwaway test `tests/test_llm_async_smoke.py` with one
  `@pytest.mark.anyio` async test that awaits `asyncio.sleep(0)` and asserts true
  **Result: written, then deleted in T011.**
- [X] T009 Run it with `uv run pytest tests/test_llm_async_smoke.py` and confirm it fails or
  errors for the expected reason (no `anyio_backend` fixture, so the trio variant is requested and
  trio is not installed). Record the message
  **Result: it did NOT fail; it passed (`test_async_tests_run[asyncio]`). Reason: the anyio
  plugin's own `anyio_backend` fixture is parametrized with the backends that are installed
  (`params=get_available_backends()`), and only asyncio is installed, so no fixture of ours is
  needed. The planned red step did not happen; recorded here as the constitution asks.**
- [X] T010 (AI may draft) Add a session-scoped `anyio_backend` fixture returning `"asyncio"` to
  `tests/conftest.py`
  **Result: skipped on purpose (not needed, see T009). If trio is ever installed, async tests
  would run twice (asyncio and trio); add the fixture then.**
- [X] T010a (AI may draft) Add an `autouse` fixture to `tests/conftest.py` that blocks real network
  access so any accidental real call fails loudly (FR-019, SC-003); confirm the existing suite
  still passes with it
  **Result: the first version, replacing `socket.socket`, broke 128 tests (asyncio and the test
  client create sockets, even to localhost on Windows). The second version, blocking only
  `connect` to non-local hosts, passed the suite but was proven NOT to stop async HTTP on Windows
  (the call timed out against the real network, because the Windows event loop does not use
  `socket.connect`). Final version, `block_network` in `tests/conftest.py`: socket creation stays
  allowed; remote `connect`/`connect_ex`, `getaddrinfo` and the asyncio loop's
  `create_connection`/`sock_connect` raise `RuntimeError("network access in a unit test")`.
  Proven by `tests/test_network_guard.py` (4 tests: sync IP, name lookup, async IP, async
  hostname). Suite: 247 passed.**
- [X] T011 Run the smoke test again and confirm green, then delete
  `tests/test_llm_async_smoke.py` (the real async tests below cover it). If the anyio plugin
  cannot be made to work, use the fallback in research.md section 9 (`asyncio.run` inside sync
  tests) and say so in the commit
  **Result: green with the guard active; file deleted. The async guard tests in
  `tests/test_network_guard.py` now exercise the anyio plugin. No fallback needed.**

**Checkpoint**: async tests run; US1 can start.

---

## Phase 3: User Story 1 - Ask a model through one provider-neutral interface (Priority: P1)

**Goal**: Immutable validated request/response types and the `LLMClient` Protocol.

**Independent Test**: Build requests and responses, see invalid ones rejected, see responses
frozen, and see a class with the right method count as an `LLMClient`.

- [X] T012 [P] [US1] Write `tests/test_llm_models.py` (sync) covering, from
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
- [X] T013 [P] [US1] Write `tests/test_llm_client_protocol.py` (sync): a tiny class with an
  `async def complete(self, request)` is an instance of `LLMClient` (runtime-checkable
  Protocol); a class without `complete` is not
- [X] T014 [US1] Run both files and confirm red (import errors for the missing package modules).
  Record the reason
  **Result: both files fail at collection, for the expected reason: `ModuleNotFoundError: No
  module named 'disputes.llm.models'` and `... 'disputes.llm.client'`. `ruff` reports one
  import-order finding in `tests/test_llm_models.py` because the module it imports does not
  exist yet; it should disappear after T015.**
- [X] T015 [US1] (owner) Implement `src/disputes/llm/models.py`: `Role`, `Message`, `LLMRequest`,
  `StopReason`, `TokenUsage`, `LLMResponse`, all frozen with `extra="forbid"`, exactly as in
  data-model.md (no sampling fields; `messages` is a `tuple[Message, ...]`)
- [X] T016 [US1] (owner) Implement `src/disputes/llm/client.py`: the `@runtime_checkable`
  `LLMClient` Protocol with `async def complete(self, request: LLMRequest) -> LLMResponse`
  **Result: written by the assistant at the owner's request (the owner must still be able to
  explain every line before committing). T015 and T016 together: 36 tests green.**
- [X] T017 [US1] Run `uv run pytest tests/test_llm_models.py tests/test_llm_client_protocol.py`
  and `uv run ruff check .`; confirm green and clean. Be ready to explain why the models are frozen
  and why `messages` is a tuple
  **Result: 36 passed (models 34 + protocol 2); full suite 283 passed; `ruff check .` clean.**

**Checkpoint**: US1 complete and independently testable.

---

## Phase 4: User Story 3 - Failures in one vocabulary, ready for retries (Priority: P2)

**Goal**: The service's own exception family with a `retryable` flag. (Translating provider
failures into it is tested in Phase 6 with the `[US3]` label.)

**Independent Test**: Each exception is an `LLMError`, and its `retryable` flag has the intended
value without creating an instance.

- [X] T018 [US3] Write `tests/test_llm_errors.py` (sync): the five subclasses are subclasses of
  `LLMError`; `retryable` read on the class (no instance) is `True` for `LLMRateLimitError`,
  `LLMTimeoutError`, `LLMProviderUnavailableError` and `False` for `LLMAuthenticationError`,
  `LLMBadRequestError` and the base `LLMError` (FR-010); `status_code` and `request_id` default to
  `None` and can be set through the constructor; `str(exc)` is the message given;
  `LLMConfigurationError` is **not** a subclass of `LLMError`; `catch LLMError` does not catch it
  **Result: `tests/test_llm_errors.py` written (20 test cases).**
- [X] T019 [US3] Run it and confirm red (module missing). Record the reason
  **Result: fails at collection with `ImportError` on `disputes.llm.errors`, the expected reason.**
- [X] T020 [US3] (owner) Implement `src/disputes/llm/errors.py` with the hierarchy in
  data-model.md: `retryable` as a class attribute, optional `status_code` and `request_id`
  attributes, and a separate `LLMConfigurationError`
  **Result: `src/disputes/llm/errors.py` written by the assistant at the owner's request (the owner must still be able to explain every line before committing).**
- [X] T021 [US3] Run `uv run pytest tests/test_llm_errors.py` and `uv run ruff check .`; confirm
  green and clean
  **Result: 20 passed; full suite 303 passed; `ruff check .` clean.**

**Checkpoint**: US3 vocabulary ready; the fake and the adapter can use it.

---

## Phase 5: User Story 2 - Test code that uses the client without a network (Priority: P1)

**Goal**: `FakeLLMClient` in `tests/` with scripted answers, recorded calls and simulated
failures.

**Independent Test**: Script two answers and one failure, make three calls, and check order,
the raised failure and the recorded requests.

- [X] T022 [US2] Write `tests/test_llm_fake.py` (async, `@pytest.mark.anyio`), importing
  `from fake_llm import FakeLLMClient, FakeScriptExhaustedError`: scripted responses come back in
  order; every request is recorded in `calls`, in order, equal to what was sent; a scripted
  failure of each of the six kinds (authentication, bad request, rate limit, timeout, provider
  unavailable, base) is raised as that exact class (FR-011); a response then a failure then a
  response works in sequence; an empty script raises `FakeScriptExhaustedError`, which is not an
  `LLMError`; the fake is an `LLMClient`; the request's messages are unchanged after the call;
  the `fake_llm` fixture gives a fresh instance per test; no network: monkeypatch
  `socket.socket` to raise, use the fake, and assert nothing raised (FR-019)
  **Result: `tests/test_llm_fake.py` written (16 test cases, 12 async with the anyio marker).**
- [X] T023 [US2] Run it and confirm red (`fake_llm` missing). Record the reason
  **Result: fails at collection with `ModuleNotFoundError: No module named 'fake_llm'`, the expected reason.**
- [X] T024 [US2] (AI may draft) Implement `tests/fake_llm.py`: `FakeLLMClient` with a queue,
  `will_return(response)`, `will_fail(error)`, `calls`, `complete`, plus
  `FakeScriptExhaustedError` (see research.md section 8). Keep it small enough to read in one
  sitting
  **Result: `tests/fake_llm.py` written. `calls` is recorded before the script is checked, so an exhausted call is still visible in `calls`.**
- [X] T025 [US2] (AI may draft) Add the `fake_llm` fixture to `tests/conftest.py`, returning a
  new `FakeLLMClient()`
  **Result: `fake_llm` fixture added to `tests/conftest.py`.**
- [X] T026 [US2] Run `uv run pytest tests/test_llm_fake.py` and `uv run ruff check .`; confirm
  green and clean
  **Result: 16 passed; full suite 319 passed; `ruff check .` clean. Ruff treats `fake_llm` as first-party (because `src` includes `tests`), so it sorts with the `disputes` imports; fixed with `ruff check --select I --fix`.**

**Checkpoint**: US1, US3 and US2 work with no key and no network.

---

## Phase 6: User Story 4 - Anthropic adapter, settings and the manual real call (Priority: P2)

**Goal**: Settings read from the environment, the adapter with retries off, failure translation,
and one documented real call.

**Independent Test**: With the real SDK against a mock HTTP transport: success maps to the
neutral response, every failure kind maps to the right exception after exactly one request, and
the key never appears. Separately, one manual real call.

### Settings

- [X] T027 [US4] Write `tests/test_llm_settings.py` (sync; use `monkeypatch` and pass
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
  **Result: `tests/test_llm_settings.py` written (12 test cases incl. the subprocess import test).**
- [X] T028 [US4] Run it and confirm red (module missing). Record the reason
  **Result: fails at collection with `ModuleNotFoundError: No module named 'disputes.llm.settings'`, the expected reason.**
- [X] T029 [US4] (owner) Implement `src/disputes/llm/settings.py`: `LLMSettings(BaseSettings)`
  with the three fields and env names from data-model.md, ignoring unknown variables, and a
  `load_settings(env_file=...)` function that builds it on demand (never at import) and converts a
  validation error into `LLMConfigurationError` naming the variable, built from the field name and
  never from the raw input
  **Result: `src/disputes/llm/settings.py` written by the assistant at the owner's request (the owner must still be able to explain every line before committing). `load_settings` raises the configuration error after the `except` block, so no validation error (which carries the input) is attached.**
- [X] T030 [US4] Run `uv run pytest tests/test_llm_settings.py` (all but the subprocess import
  test should pass) and `uv run ruff check .`
  **Result: 11 passed; the only failure was the subprocess import test, as expected until the adapter module existed (it passed in T036).**

### Adapter

- [X] T031 [US4] Write the success-path tests in `tests/test_llm_anthropic_adapter.py` (async,
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
  **Result: success-path tests written in `tests/test_llm_anthropic_adapter.py`, including the SC-008 `ask(client)` test. Observed with `anthropic 2.10.0`: the key travels as `Authorization: Bearer <key>`, so the test asserts that header (not `x-api-key`).**
- [X] T032 [US4] [US3] In the same file add the failure-translation tests: for each row of the
  table in research.md section 4 parametrize the HTTP status (401, 403 to authentication; 400, 404,
  422 to bad request; 429 to rate limit; 500, 502, 503, 529 to provider unavailable; 418 to the
  base `LLMError`), HTTP 408 and a `httpx2.ReadTimeout` raised by the transport to
  `LLMTimeoutError`, 409 to the base `LLMError` (not retryable), and a `httpx2.ConnectError` to
  `LLMProviderUnavailableError`; for each assert the exact class, the
  `retryable` value, `status_code`, `request_id` from the `request-id` header when present, and
  that `__cause__` and `__context__` are `None` (raised outside the `except` block, research
  section 4)
  **Result: failure-translation tests written: 13 HTTP statuses, 2 transport errors, the retryable flags and the no-cause/no-context check.**
- [X] T033 [US4] In the same file add the retries-off and key-safety tests: for the 500, 429 and
  timeout cases the transport handler was called exactly once (SC-005, FR-013); the SDK client's
  retries attribute (the one found in T005, read through the adapter's `_client` attribute) is `0`
  and its timeout equals the configured seconds
  (FR-015); for every failure kind, the sentinel key is not in `str(exc)`, `repr(exc)`, the
  formatted traceback (`traceback.format_exception`), `repr(adapter)`, `str(adapter)` or captured
  log records at DEBUG level (FR-016); `from_env()` with all variables set builds the adapter and
  with `ANTHROPIC_API_KEY` missing raises `LLMConfigurationError` naming it (FR-017)
  **Result: retries-off, single-attempt and key-safety tests written, plus `from_env` tests (run in a temp directory so a local `.env` is never read).**
- [X] T034 [US4] Run the file and confirm red (module missing), then record the reason
  **Result: fails at collection with `ModuleNotFoundError: No module named 'disputes.llm.anthropic_adapter'`, the expected reason.**
- [X] T035 [US4] (owner) Implement `src/disputes/llm/anthropic_adapter.py`: `AnthropicLLMClient`
  built from `api_key: SecretStr`, `model`, `timeout_seconds` and an optional `http_client`
  (tests only); it creates `AsyncAnthropic(api_key=<secret value, read once>, max_retries=0,
  timeout=...)` and keeps it in the attribute `self._client` (tests read it); `from_env()` uses `load_settings()`; `complete` calls the SDK once, reads only
  `text` blocks, maps usage, model and stop reason, and translates failures per research.md
  section 4 (timeout class tested before connection class) with our own message, status code and
  request id, raised after the `except` block so no cause or context is attached; give the class
  a `__repr__` that shows no key
  **Result: `src/disputes/llm/anthropic_adapter.py` written by the assistant at the owner's request (the owner must still be able to explain every line before committing). One deviation from the task text: the service error is raised after the `except` block (not `from None` inside it), so neither `__cause__` nor `__context__` holds the provider error; research.md section 4 updated.**
- [X] T036 [US4] Run `uv run pytest tests/test_llm_anthropic_adapter.py
  tests/test_llm_settings.py` (now including the subprocess import test) and
  `uv run ruff check .`; confirm green and clean. If a test fails because a detail of the SDK
  differs from research.md, fix research.md with the observed fact, not just the code
  **Result: adapter and settings tests all green; full suite 380 passed; `ruff check .` clean and the new files formatted. The one red found on the way was the test's own wrong assumption about the key header (see T031).**

### Manual real call

- [X] T037 [US4] (AI may draft) Write `scripts/manual_anthropic_call.py` (outside `tests/`, so
  pytest never collects it): refuses to run if the `CI` environment variable is set; builds the
  adapter with `from_env()`; sends one short synthetic prompt with a small `max_tokens`; prints
  text, input and output tokens, model and stop reason; on `LLMError` prints the class name,
  `retryable`, `status_code` and `request_id`, never the key. Confirm `uv run pytest` does not
  collect it
  **Result: `scripts/manual_anthropic_call.py` written. Dry-run without a key prints `ANTHROPIC_API_KEY is not set; LLM_MODEL is not set` (exit 2); with `CI=1` it refuses to run (exit 2); `pytest --collect-only` does not collect it. No real call was made.**
- [X] T038 [US4] Run the script once with your own key (quickstart section 4). Do not paste the
  key anywhere. Note the date, and the real output
  **Result: run by the owner on 2026-11-17. First attempt: `LLM_MODEL` still held the placeholder, so the provider answered 404 and the adapter raised `LLMBadRequestError` (not retryable, with status and request id, no key). Second attempt with `claude-sonnet-5-5`: answer returned, 43 input tokens, 63 output tokens, model `claude-sonnet-5-5`, stop reason `completed`.**
- [X] T039 [US4] Create `docs/evidence/llm-client-anthropic.md` with the date, the exact command,
  the prompt and the real output of T038 (text, tokens, model, stop reason). State plainly that it
  is one manual call, not run in CI, and that the timeout default of 60 s is not validated by it
  (research.md section 6); if the call timed out or failed, record that as it happened
  **Result: `docs/evidence/llm-client-anthropic.md` created from the owner's pasted output, with the successful call, the earlier 404 attempt, and an explicit list of what the call does not show (latency, thinking tokens, cost, other failure kinds).**
- [X] T040 [US4] Check the evidence file and the whole repository for secrets: search for
  `sk-ant`, `ANTHROPIC_API_KEY=` followed by a value, and the test sentinel outside `tests/`; fix
  anything found before committing
  **Result: scan clean. No `sk-ant` strings; the only key-like strings are the test sentinel inside `tests/`; `.env` is ignored and untracked; the placeholder in `.env.example` is the only assignment outside tests. A comparison against the real key held in the local `.env` (kept in memory only, never printed) found it in no other file, evidence file included.**

**Checkpoint**: all four stories work; one real call is documented.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T041 (owner) Fill `src/disputes/llm/__init__.py` with re-exports of the interface, models,
  errors and settings, but **not** the adapter (importing the package must not load the SDK).
  Add a one-line test in `tests/test_llm_models.py` that `from disputes.llm import LLMClient,
  LLMRequest, LLMResponse, LLMError` works
  **Result: two tests added to `tests/test_llm_models.py` first: the package exports the public pieces (red: `ImportError`) and importing `disputes.llm` does not load the `anthropic` SDK (passed already while the package was empty, so it only guards against regressions). Then `src/disputes/llm/__init__.py` written (written by the assistant at the owner's request). 36 passed in that file.**
- [X] T042 (AI may draft) Update `README.md`: the Roadmap row for feature 003 and a short "LLM
  client" section stating only what exists and is tested (interface, fake in `tests/`, Anthropic
  adapter, environment variables, how to run the manual call) with retries, Azure adapter and
  any endpoint labelled planned. Constitution VI
  **Result: README updated: new "LLM client" section (what exists and is tested), configuration table and the manual call, the limits line, and the roadmap (003 Done; the Azure OpenAI adapter split into its own Planned row). No figures were added that were not measured.**
- [X] T043 (AI may draft) Update `docs/ARCHITECTURE.md` with the `disputes.llm` package: the
  interface, the one-SDK-import rule, the failure table and the "no hidden retries" decision
  **Result: `docs/ARCHITECTURE.md` updated: diagram labels, the `disputes.llm` modules in the "what exists" table, four new design decisions (one attempt, secret key and error raising, settings timing, one adapter per provider) and the testing approach (socket guard, in-memory transport, manual evidence).**
- [X] T044 Run the full suite and lint: `uv run pytest` and `uv run ruff check .`; record the
  passing count (compare with T001) and that no test needed a key or the network (the socket
  guard from T010a enforces it; also run once with `ANTHROPIC_API_KEY` unset)
  **Result: `uv run pytest`: 382 passed; with `ANTHROPIC_API_KEY`, `LLM_MODEL` and `LLM_TIMEOUT_SECONDS` removed from the environment: 382 passed; `ruff check .` clean. The count is 243 (T001) plus the tests of this feature. No test used a key or the network (the guard in `tests/conftest.py` enforces it).**
- [X] T045 Check SC-001 (deterministic over 100 runs): run
  `for i in $(seq 1 100); do uv run pytest -q tests/test_llm_fake.py || break; done` and record that
  all passed; check SC-002 to SC-008 against the tests and record where each is covered
  (tracing table in the PR description)
  **Result: SC-001: `tests/test_llm_fake.py` run 100 times in separate processes, 0 failed. Coverage of the other criteria: SC-002 `test_llm_errors.py` (flags), `test_llm_fake.py` (six kinds raised), `test_llm_anthropic_adapter.py` (translation); SC-003 the guard plus `test_network_guard.py`, and the suite passes with the variables unset; SC-004 `test_llm_settings.py` (printed settings) and the adapter key-safety test (error text, traceback, `repr`, logs); SC-005 `test_a_failing_call_is_attempted_exactly_once`; SC-006 the import-without-key subprocess test and `test_from_env_without_a_key_names_the_missing_variable`; SC-007 `docs/evidence/llm-client-anthropic.md`; SC-008 `test_a_caller_works_the_same_with_the_fake_and_with_the_adapter`. Put this table in the PR description.**
- [X] T046 Walk through [quickstart.md](quickstart.md) sections 1 to 3 as written and note any
  step that does not work as described; fix the document
  **Result: sections 1 to 3 walked through as written. Section 1: 133 passed; section 2 worked in a temporary test (deleted); section 3: import ok and the error names `ANTHROPIC_API_KEY` and `LLM_MODEL`. Fixes to the document: the test list in section 1 now includes the protocol and network-guard tests, and section 3 mentions that `LLM_MODEL` is named too.**
- [X] T047 Update `CLAUDE.md` per "Al cerrar una feature": "Estado actual", the roadmap row 003
  (the Azure OpenAI adapter in the description stays pending), and move to "Decisiones ya
  tomadas" what was confirmed (the `LLMClient` shape, `retryable` flag, `max_retries=0`, key as
  `SecretStr`, fake in `tests/`, configuration error not an `LLMError`). Keep the file's language
  convention
  **Result: `CLAUDE.md` updated: current state (feature 003 done, pending PR; Azure adapter pending; next step), the roadmap row (Azure split into its own row) and six confirmed decisions moved to "Decisiones ya tomadas". It says "pendiente de PR" because T048 is not done; change it to merged after the PR.**
- [X] T048 Open the PR from `feat/003-llm-client` into `develop`; wait for CI green (tests,
  lint, and the existing image job, which must still start the container with no key set); fix
  anything red; merge only when green
  **Result: PR #6 opened from `feat/003-llm-client` into `develop` with the success-criteria traceability table; `CLAUDE.md` updated with the PR number; CI result and merge recorded in the PR.**

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
