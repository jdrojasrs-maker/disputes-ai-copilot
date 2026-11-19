---

description: "Task list for the Azure OpenAI adapter"
---

# Tasks: Azure OpenAI Adapter for the LLM Client

**Input**: Design documents from `/specs/004-azure-openai-adapter/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/azure-adapter-contract.md

**Tests**: REQUIRED. Constitution principle I (NON-NEGOTIABLE, v2.0.0): write the test first, run
it, and confirm it fails for the expected reason (red) before writing the code that makes it pass
(green). Do not combine a test task and its implementation task into one step. When a test already
passes at its red run (for example the shared tests against the fake and the Anthropic adapter),
record that and why; it then only guards against regressions. **Budget: 10 test functions** (plan,
"Test plan"). A test the owner cannot explain line by line is not merged.

**Organization**: Grouped by user story. US1 and US2 are P1, US3 and US4 are P2, US5 is P3. Phases
are ordered by dependency: US1 builds the adapter's happy path, US2 puts the shared suite on top
of it, US3 adds failures, US4 adds settings, US5 documents one real call.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 = ask an Azure-hosted model through the same interface, US2 = one shared
  behavior suite, US3 = failures in the service's vocabulary, US4 = configuration from the
  environment, US5 = one real call as evidence
- All paths are relative to the repository root. Commands: `uv run pytest`, `uv run ruff check .`
- **Who writes what** (CLAUDE.md): tasks tagged *(owner)* are core logic (adapter, settings,
  tests of rules) that the project owner writes and must be able to explain line by line before
  committing. Tasks tagged *(AI may draft)* are scaffolding, scripts or documentation the
  assistant can generate; the owner reviews them. Untagged tasks are runs and checks.
- Nothing is committed, pushed or merged without the owner asking for it in that message.
- Not in this feature: retries and backoff, streaming, tool use, structured output, sampling
  parameters, Microsoft Entra authentication, any HTTP endpoint using the client, caching, cost
  calculation. Tests of features 001-003 and `tests/fake_llm.py` are NOT modified.

## Phase 1: Setup

**Purpose**: Confirm the baseline, branch, add the dependency, check install-time facts

- [X] T001 On the current branch run `uv sync`, `uv run pytest` and `uv run ruff check .`; record
  the number of passing tests (read it from the output, do not assume) and that lint is clean
  **Result (2026-11-18, `feat/004-azure-openai-adapter`, same code as `develop`): 382 passed in 16.84 s. `ruff check .` clean for tracked files; its only finding is the untracked scratch `scripts/first_azure_call.py` (import order), see T005.**
- [X] T002 Create the implementation branch `feat/004-azure-openai-adapter` from `develop`; decide
  with the owner how the spec artifacts (`specs/004-azure-openai-adapter/`, `.specify/feature.json`)
  reach it (docs commit first, as in feature 003)
  **Done: branch created from `develop`; spec artifacts committed as `9c50395`.**
- [X] T003 Add the dependency with `uv add openai`; check that only `pyproject.toml` and
  `uv.lock` changed; record the installed version in `specs/004-azure-openai-adapter/research.md`
  (D2)
  **Result: `openai 3.55.1` (`openai>=3.55.1` in `pyproject.toml`); only `pyproject.toml` and `uv.lock` changed.**
- [X] T004 [P] Re-check, with throwaway commands in the scratch area (not committed), the SDK
  facts of research.md D4 and D6 (first read in a scratch environment) against the version
  actually installed in the project: `finish_reason`
  values, `content` and `usage` optional, `APITimeoutError` subclass of `APIConnectionError`, 408
  is a plain `APIStatusError`, `request_id` on the error, `AsyncOpenAI(..., max_retries=0)` keeps
  `max_retries == 0` and `timeout` readable. Replace any difference in research.md
  **Result: all facts confirmed on 3.55.1 in the project environment: `finish_reason` values, `content` and `usage` optional, `APITimeoutError` subclass of `APIConnectionError`, no `RequestTimeoutError`, `max_retries == 0` and `timeout` readable, and a 408 raises a plain `APIStatusError` (`request_id` is `None` when the header is absent). No change to research.md D4/D6.**
- [ ] T005 [P] Decide the future of the untracked scratch `scripts/first_azure_call.py` with the
  owner (delete, or keep out of the commit). It is replaced by T031

**Checkpoint**: baseline green, `openai` installed, SDK facts confirmed

---

## Phase 2: User Story 1 - Ask an Azure-hosted model through the same interface (Priority: P1)

**Goal**: `AzureOpenAILLMClient` implements `LLMClient`: it sends the request in Azure's shape and
returns the neutral response.

**Independent Test**: With `httpx2.MockTransport`, send a request and see the outgoing body and
the mapped response (text, tokens, versioned model name, stop reason).

### Tests for US1 (write first, confirm red)

- [ ] T006 [US1] *(owner)* Create `tests/test_llm_azure_adapter.py` with the helpers it needs: a
  `Wire` recorder like the one in `tests/test_llm_anthropic_adapter.py` (copy the idea, do not
  import from that file), a `completion_body(...)` builder for the Azure chat-completions JSON
  (`choices[0].message.content`, `choices[0].finish_reason`, `usage.prompt_tokens`,
  `usage.completion_tokens`, `usage.total_tokens`, `model`), and a `build(wire)` that constructs
  `AzureOpenAILLMClient(api_key=SecretStr(SENTINEL), base_url=..., deployment=..., timeout_seconds=...,
  http_client=openai.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(wire)))`
- [ ] T007 [US1] *(owner)* Test 5 in `tests/test_llm_azure_adapter.py`: the outgoing body has
  `max_completion_tokens` equal to the request's maximum, has no `max_tokens`, has `model` equal to
  the deployment, has the system prompt as a first message with role `system` (and none when there
  is no system prompt), keeps the message order, has none of `temperature`, `top_p`, `top_k`, and
  the request carries the key as a bearer header (observe the real header name first, as was done
  for Anthropic). Run it: it must fail because the module does not exist (red)
- [ ] T008 [US1] *(owner)* Test 6 in `tests/test_llm_azure_adapter.py`: parameterized over
  `finish_reason` — `stop` gives completed; `length` gives max tokens, with the cut text returned
  and no exception; `content_filter`, `tool_calls` give other. Also assert that the model name
  returned is the one in the answer, not the deployment, and that tokens come from
  `prompt_tokens` and `completion_tokens`: the simulated usage carries a non-zero
  `completion_tokens_details.reasoning_tokens` smaller than `completion_tokens`, and the test
  asserts `output_tokens == completion_tokens` (no adjustment, spec US1 scenario 6). Run: red

### Implementation for US1

- [ ] T009 [US1] *(owner)* Create `src/disputes/llm/azure_openai_adapter.py`: `AzureOpenAILLMClient`
  with a keyword-only `__init__(api_key: SecretStr, base_url: str, deployment: str,
  timeout_seconds: float, http_client=None)` that builds `openai.AsyncOpenAI(api_key=<unwrapped
  once>, base_url=base_url, max_retries=0, timeout=timeout_seconds, http_client=http_client)`;
  `__repr__` shows the deployment and never the key. This is the only module that imports `openai`
- [ ] T010 [US1] *(owner)* In the same file implement `complete`: build the messages (system first
  when present), call `chat.completions.create(model=<deployment>,
  messages=..., max_completion_tokens=request.max_tokens)`, map text from `choices[0].message.content`,
  usage from `prompt_tokens`/`completion_tokens`, model from the answer, and `finish_reason` via a
  module-level table (`stop` completed, `length` max tokens, anything else other)
- [ ] T011 [US1] Run T007 and T008: they pass (green). Run `uv run ruff check .`

**Checkpoint**: Azure happy path works with simulated transport. US1 done (2 test functions)

---

## Phase 3: User Story 2 - One shared behavior suite proves every implementation (Priority: P1)

**Goal**: The same behavior tests run against the fake, the Anthropic adapter and the Azure
adapter, with no network.

**Independent Test**: `uv run pytest tests/test_llm_contract.py` reports each shared test three
times (once per implementation), all green.

### Tests for US2 (write first, confirm red)

- [ ] T012 [US2] *(owner)* Create `tests/llm_harness.py`: a `Harness` per implementation exposing
  `client`, `script_answer(text, input_tokens, output_tokens, model, stop)` and `calls` (number of
  provider calls). Three builders: fake (`will_return`), Anthropic (handler returning
  an Anthropic message body, built like `tests/test_llm_anthropic_adapter.py` does), Azure
  (handler returning a chat-completions body). Do not edit `tests/fake_llm.py` or the Anthropic
  test file. Add a pytest fixture parameterized over the three builders (ids `fake`, `anthropic`,
  `azure`) in `tests/test_llm_contract.py`
- [ ] T013 [US2] *(owner)* Test 1 in `tests/test_llm_contract.py`: an answer comes back as the
  neutral response (text, input and output tokens, answering model, completed) and the client is an
  `LLMClient`. Run: green for fake and Anthropic at once, green for Azure after T011; record that
  in the task notes (the test guards regressions for the first two)
- [ ] T014 [US2] *(owner)* Test 2 in `tests/test_llm_contract.py`: an answer cut by the token limit
  is returned with stop reason max tokens and the text produced so far; no exception
- [ ] T015 [US2] *(owner)* Test 3 in `tests/test_llm_contract.py`: the request is equal to a deep
  copy of itself after a call, and two concurrent calls (`asyncio.gather`) each get their own
  answer (the stand-in answers with the text of the last user message)
- [ ] T016 [US2] Run `uv run pytest tests/test_llm_contract.py`: 9 cases pass (tests 1-3 x 3
  implementations; test 4 is added in US3). If a case fails for Azure, fix the adapter (not the
  test) unless the test is wrong; record what you found
- [ ] T017 [US2] Make the shared suite catch a broken implementation: temporarily break one
  mapping in the Azure adapter (for example swap input and output tokens), see test 1 fail for
  `azure` only, then restore it. Record the result (SC-002 evidence); do not commit the break

**Checkpoint**: three implementations pass one suite. US2 done (3 test functions, 9 cases)

---

## Phase 4: User Story 3 - Handle Azure failures in the service's own vocabulary (Priority: P2)

**Goal**: Every provider failure becomes the matching service error; one attempt per call; no key
or provider text in any error; an answer with no text raises the base error.

**Independent Test**: Simulate each failure with `MockTransport` and check class, retryable flag,
number of calls and message content.

### Tests for US3 (write first, confirm red)

- [ ] T018 [US3] *(owner)* Test 4 in `tests/test_llm_contract.py` (shared, parameterized over 6
  failure kinds x 3 implementations): authentication, bad request, rate limit, timeout, provider
  unavailable, other raise the matching service error with the right `retryable` flag. The harness
  gets `script_failure(kind)`: the fake uses `will_fail`; the adapters use HTTP 401, 400, 429, a
  transport read timeout, 503 and 418. Run: red for Azure (no translation yet), green for the
  other two
- [ ] T019 [US3] *(owner)* Test 7 in `tests/test_llm_azure_adapter.py`: parameterized — empty
  `choices`, `content` null with `finish_reason` `content_filter`, `content` of blank text, and a
  missing `usage` — each raises the base `LLMError` (exactly that class, not retryable) with a
  message that does not include the provider's text. Run: red
- [ ] T020 [US3] *(owner)* Test 8 in `tests/test_llm_azure_adapter.py`: parameterized over 500, 429,
  a transport read timeout and a connection error, the provider is called exactly once; plus the SDK
  client has `max_retries == 0` and the configured timeout. Run: red/green as the code allows;
  record which
- [ ] T021 [US3] *(owner)* Test 9 in `tests/test_llm_azure_adapter.py`: for 401, 400, 429, 500, 418,
  timeout and connection failures, and for the no-text error, the key sentinel is absent from
  `str`, `repr`, the formatted traceback, the client's `repr` and the captured log, and the
  error's `__cause__` and `__context__` are `None`. Run: red

### Implementation for US3

- [ ] T022 [US3] *(owner)* In `src/disputes/llm/azure_openai_adapter.py` add `_translate(error)`
  following the table in contracts/azure-adapter-contract.md: test `APITimeoutError` before
  `APIConnectionError`; a plain `APIStatusError` with status 408 is a timeout; 401 and 403
  authentication; 400, 404 and 422 bad request; 429 rate limit; 5xx provider unavailable; anything
  else the base `LLMError`. Messages are `"Azure OpenAI ... (HTTP <status>)"` text written here,
  never `str(error)`; pass `status_code` and `request_id`
- [ ] T023 [US3] *(owner)* In `complete`, wrap only the SDK call in `try/except openai.OpenAIError`,
  store the translated error in a variable and raise it after the `except` block (same technique
  and comment as the Anthropic adapter), so no `__context__` holds the request
- [ ] T024 [US3] *(owner)* After the call, raise `LLMError("Azure OpenAI returned no text")` when
  `choices` is empty or the first choice's `content` is null or blank, and
  `LLMError("Azure OpenAI returned no token usage")` when `usage` is missing; both fixed service
  text, raised outside any `except`
- [ ] T025 [US3] Run T018 through T021: all green. Run the whole contract suite: 27 cases
  (tests 1-3 x 3 implementations, plus test 4 x 6 kinds x 3) plus the Azure file pass

**Checkpoint**: failures, one attempt, no leaks, no-text handling. US3 done (4 test functions)

---

## Phase 5: User Story 4 - Configure the adapter safely from the environment (Priority: P2)

**Goal**: Settings are read from the environment when the adapter is built; a bad setting names its
variable; the key is a secret; import never fails.

**Independent Test**: Build with each variable missing in turn and with an invalid URL; the test
file imports the module with no `AZURE_*` variables set.

### Tests for US4 (write first, confirm red)

- [ ] T026 [US4] *(owner)* Test 10 in `tests/test_llm_azure_adapter.py`, parameterized over 4 cases
  (`AZURE_OPENAI_BASE_URL` missing, `AZURE_OPENAI_API_KEY` missing, `AZURE_OPENAI_DEPLOYMENT`
  missing, `AZURE_OPENAI_BASE_URL=not a url`): using `monkeypatch` and `tmp_path` (chdir, so no
  local `.env` is read, as in the Anthropic tests), `AzureOpenAILLMClient.from_env()` raises
  `LLMConfigurationError` whose message names that variable and does not contain the supplied
  value. No subprocess: the module is imported at the top of the test file, in an environment
  without `AZURE_*` variables in CI, which is what shows it does not fail at import (FR-013);
  note this in a comment. Run: red

### Implementation for US4

- [ ] T027 [US4] *(owner)* In `src/disputes/llm/settings.py` add `AzureOpenAISettings`
  (`BaseSettings`, `env_file=".env"`, `extra="ignore"`) with exactly these fields and rules
  (data-model.md): `azure_openai_base_url` required, valid HTTP(S) URL; `azure_openai_api_key`
  required, `SecretStr`; `azure_openai_deployment` required, `min_length=1`; `llm_timeout_seconds`
  default 60, `gt=0`. Add `load_azure_settings(env_file=".env")` that raises
  `LLMConfigurationError` naming the variable, built from the variable name and the rule text and
  never from the supplied value. Reuse the existing error-building code by extracting it to a small
  private helper shared with `load_settings`; the behavior and the tests of `load_settings` must not
  change (`tests/test_llm_settings.py` runs unmodified)
- [ ] T028 [US4] *(owner)* In `src/disputes/llm/azure_openai_adapter.py` add
  `AzureOpenAILLMClient.from_env()` using `load_azure_settings()` (never at import)
- [ ] T029 [US4] [P] *(AI may draft)* Add the Azure variables to `.env.example` with placeholders
  only (`AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`; a note that
  `LLM_TIMEOUT_SECONDS` is shared and `LLM_MODEL` is not used by this adapter). No real value
- [ ] T030 [US4] Run T026: green. Run `uv run pytest tests/test_llm_settings.py`: unchanged and green.
  Optionally check by hand that `repr(load_azure_settings())` shows the key masked (it is
  Pydantic's `SecretStr`; not a test, the framework guarantees it)

**Checkpoint**: configuration safe and lazy. US4 done (1 test function, 4 cases). All 10 test
functions exist

---

## Phase 6: User Story 5 - Document one real call as evidence (Priority: P3)

**Goal**: One real call recorded under `docs/evidence/`, with its limits, not run in CI.

**Independent Test**: Read the evidence file; confirm CI does not run the script.

- [ ] T031 [US5] [P] *(AI may draft)* Create `scripts/azure_openai_call.py` in the style of
  `scripts/manual_anthropic_call.py`: build the adapter with `from_env()`, send one request
  (system prompt, one question, a maximum of output tokens), print text, input and output tokens,
  the model name reported, the stop reason and `repr(client)`; never print the key; on an
  `LLMError` print class, `retryable`, `status_code`, `request_id`. Do not add `python-dotenv` as a
  dependency (settings already read `.env`)
- [ ] T032 [US5] Owner runs the script once against the real deployment with their local `.env`
  (never committed) and keeps the printed output. Confirm in that run whether the `system` role was
  accepted (plan, open items): if it is rejected, switch to the accepted role in the adapter, fix
  the test of T007 first (red), then the code (green), and record the change
- [ ] T033 [US5] *(AI may draft)* Write `docs/evidence/llm-client-azure-openai.md` from the real
  output: date, deployment type, script path and command, the output as printed, what it shows, and
  **what it does not show**: latency, cost, failure kinds other than those actually observed,
  reasoning-heavy answers (reasoning tokens counted inside completion tokens is unverified),
  content-filter blocks, the `system`-versus-`developer` finding. No secret, no resource name that
  identifies the owner's subscription
- [ ] T034 [US5] Check that `.github/workflows/ci.yml` runs only `pytest` and `ruff` (it does not
  run `scripts/`) and that the evidence document contains no key, no real endpoint and no
  subscription details (`git grep` for the key prefix and for `openai.azure.com`)

**Checkpoint**: evidence recorded and honest. US5 done

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T035 Run the whole suite and lint: `uv run pytest` and `uv run ruff check .`; record the
  number of passing tests (T001's number plus this feature's cases) and that no 001-003 test file
  changed (`git diff --stat develop -- tests/` shows only new files)
- [ ] T036 Confirm FR-016 and FR-019 mechanically: `git grep -n "import openai\|from openai"
  src/` lists only `src/disputes/llm/azure_openai_adapter.py`; `git diff develop --stat` shows no
  edits to `tests/fake_llm.py`, `tests/test_llm_*` of feature 003, or `anthropic_adapter.py`
- [ ] T037 Run the manual checks of quickstart.md sections 2 and 3 (swap the adapter in a tiny
  caller; empty-environment import; `from_env()` builds with all variables set and names the
  first missing one otherwise) and record the outcome
- [ ] T038 [P] *(AI may draft)* Update docs, claiming only what exists and is tested: README
  (the Azure adapter exists; the roadmap row), `docs/ARCHITECTURE.md` (a second adapter; the
  known inconsistency: Anthropic returns empty text when there is no text, Azure raises), and the
  "Estado actual", roadmap table and "Decisiones ya tomadas" in `CLAUDE.md` (adapter done; settings
  names; no-text decision; `max_completion_tokens`; the roadmap numbering: this feature took
  Spec Kit number 004, while the roadmap reserves 004 for intake; reconcile the table)
- [ ] T039 Review FR-021 (nothing out of scope slipped in: no retries, streaming, tools, structured
  output, sampling parameters, Entra authentication, endpoint, caching, cost calculation) by reading
  the diff. Owner explains every new test and every adapter line aloud (or in writing) before the
  commit, per the constitution's workflow rule. Open the PR to `develop` only when the owner asks;
  CI must be green before merging

---

## Dependencies & Execution Order

- Phase 1 (T001-T005) first. T003 before everything that imports `openai`; T004 and T005 are `[P]`.
- US1 (T006-T011) needs T003. Tests T006-T008 before code T009-T010.
- US2 (T012-T017) needs US1 (the Azure adapter must exist for its cases to pass).
- US3 (T018-T025) needs US1; test 4 also needs the harness from US2 (T012).
- US4 (T026-T030) needs US1 (the class exists); T027 and T028 do not depend on US3.
- US5 (T031-T034) needs US4 (`from_env`). T031 can be drafted earlier but is run after US4.
- Polish (T035-T039) last. T038 `[P]` with T037.

### Parallel opportunities

- T004 and T005 (research re-check and scratch-script decision).
- T029 (`.env.example`) alongside T027-T028.
- T031 (script draft) alongside US3/US4 work.
- T038 (docs) alongside T037.
- Test-writing within a story is not parallel: all of US1's tests share one new file.

## Implementation Strategy

- **MVP**: Phases 1-3 (US1 + US2): the adapter works on the happy path and is proven equivalent to
  the other implementations by one suite. Not shippable alone (no failure handling, no settings),
  but each later story only adds behavior and does not rework what exists.
- **Then** US3 (safety of failures), US4 (configuration), US5 (evidence).
- **Budget check**: test functions: T007, T008 (2) + T013, T014, T015 (3) + T018, T019, T020, T021
  (4) + T026 (1) = 10. Cases are more because of parameterization; the plan states this.
- **Red/green discipline**: for each test task, run it and note the failure reason before writing
  the code. Shared tests that pass at once for the fake and the Anthropic adapter are recorded as
  regression guards, not as red.

## Notes

- Total tasks: 39. Per story: Setup 5, US1 6, US2 6, US3 8, US4 5, US5 4, Polish 5.
- Known limit to record (not fix here): the Anthropic adapter returns empty text for an answer with
  no text, the Azure adapter raises; reconciling them needs a feature allowed to touch 003.
