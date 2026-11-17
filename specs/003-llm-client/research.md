# Research: LLM Client Abstraction

No `NEEDS CLARIFICATION` items remain. The items below are the decisions the spec deferred to
planning.

**Source of SDK facts.** Facts about the Anthropic Python SDK and API come from the Claude API
reference bundled with Claude Code (checked 2026-11-17), not from the live documentation site.
Items marked *(confirm on install)* must be checked against the version `uv` actually installs
before the related test is written.

## 1. Shape of the interface

- **Decision**: A `typing.Protocol` named `LLMClient` with one method,
  `async def complete(self, request: LLMRequest) -> LLMResponse`. `LLMRequest` is a frozen
  Pydantic model holding `system: str | None`, `messages: tuple[Message, ...]`, `max_tokens: int`.
- **Rationale**: The repository already sits behind a `Protocol` (decision already taken in
  `CLAUDE.md`), so this follows the same pattern. One request object keeps the signature stable
  when a later feature adds a field. The request validates itself (non-empty messages, positive
  `max_tokens`), so every implementation, including the fake, gets the same validation for free
  and FR-003/FR-004 are tested once.
- **Alternatives considered**: An abstract base class (rejected: forces inheritance, the fake and
  adapters gain nothing from shared code); `complete(messages, system=None, max_tokens=...)` with
  loose arguments (rejected: validation would have to be repeated in each implementation).

## 2. Sampling parameters are absent

- **Decision**: `LLMRequest` has no `temperature`, `top_p` or `top_k`, and `extra="forbid"` so
  passing one is a validation error, not silently ignored.
- **Verified**: The bundled reference says the current models (Claude Opus 5.5, Sonnet 5.5,
  Haiku 5.5, and the Fable line) reject them with a 400, and that from `2026-10-21` a Messages
  request sending any of them returns a 400 on every model. This confirms the premise stated in
  the spec.
- **Alternatives considered**: Accept and drop them (rejected: hides a caller's mistake).

## 3. Reading the answer (text, usage, model, stop reason)

- **Decision**: The adapter concatenates the `text` of every content block whose `type` is
  `"text"` and ignores all other block types. `LLMResponse.model` is the `model` field of the
  provider's answer (the model that actually answered), not the configured name. Usage maps
  `usage.input_tokens` and `usage.output_tokens`.
- **Why it matters**: On Claude Opus 5.5 and Sonnet 5.5 thinking is on by default, and a reply
  can contain `thinking` blocks before the text. Reading `content[0].text` would break or return
  the wrong thing. Thinking tokens count toward `max_tokens` (*confirm on install*), so a small
  limit can end with stop reason `max_tokens` and empty text. That is returned as a normal
  response (spec clarification 1), and the caller sees it through the stop reason.
- **Stop reason mapping** (neutral `StopReason`): `end_turn` and `stop_sequence` → `completed`;
  `max_tokens` → `max_tokens`; everything else (`tool_use`, `pause_turn`, `refusal`, unknown
  future values) → `other`. A `refusal` therefore arrives as `other` with whatever text exists;
  deciding what to do with it is left to a later feature.
- **Alternatives considered**: Expose the provider's raw stop string (rejected: leaks provider
  vocabulary into callers, breaks the Azure adapter's neutrality).

## 4. Failure translation

- **Decision**: One service base error `LLMError` with a class attribute `retryable: bool`, and
  five subclasses. Translation, most specific first (`APITimeoutError` is a subclass of
  `APIConnectionError`, so it must be tested before it *(confirm on install)*):

  | Provider failure (SDK class) | Service exception | `retryable` |
  |---|---|---|
  | `AuthenticationError` (401), `PermissionDeniedError` (403) | `LLMAuthenticationError` | no |
  | `BadRequestError` (400), `NotFoundError` (404, for example a wrong model name), `UnprocessableEntityError` (422) | `LLMBadRequestError` | no |
  | `RateLimitError` (429) | `LLMRateLimitError` | yes |
  | `APITimeoutError`, HTTP 408 | `LLMTimeoutError` | yes |
  | `InternalServerError` (>= 500), HTTP 529 overloaded, `APIConnectionError` (not timeout) | `LLMProviderUnavailableError` | yes |
  | any other `APIStatusError`, any other `anthropic.AnthropicError` | `LLMError` (base) | no |

- **Rationale**: Follows the SDK's own definition of what it would retry (connection errors, 408,
  429, >= 500). HTTP 409 (conflict) is not a transient failure, so it goes to the base error,
  which is not retryable. A model-name typo (404)
  is classed as bad request because retrying never fixes it.
- **Message and key safety**: Our message is our own text plus the HTTP status and the provider's
  request id, never `str(original_error)`. The exception is raised with `from None` so the
  provider exception, which holds the outgoing request and its headers (including the key), is
  not attached as `__cause__`. Cost: less debugging detail in tracebacks; the status code and
  request id are kept as attributes to make up for it.
- **Alternatives considered**: `raise ... from e` (rejected: retains an object that carries the
  key in its request headers, which error trackers may serialise).

## 5. Retries are off, and that is proven

- **Decision**: The adapter builds `AsyncAnthropic(api_key=..., max_retries=0, timeout=...)`.
- **Proof test**: Build the real SDK client with `http_client` set to an `httpx2` mock transport
  that answers 500 (and, in another case, 429) and counts requests; assert the SDK made exactly
  one request and the adapter raised the matching service exception. This tests the real SDK
  behaviour with no network (SC-005). The project already has `httpx2` in its dev group. A second,
  cheaper test asserts the configured value on the client object *(confirm on install: attribute
  name `max_retries`)*.
- **Alternatives considered**: Only asserting the constructor argument with a mock (rejected: it
  would pass even if the SDK ignored the argument).

## 6. Timeout

- **Decision**: Setting `LLM_TIMEOUT_SECONDS`, a positive float, default `60`. Passed to the SDK
  as `timeout=<seconds>`; an expiry raises `APITimeoutError`, which becomes `LLMTimeoutError`.
- **What the number means**: The SDK passes a single number as the timeout of each phase of the
  HTTP exchange, so a call can last longer than that number in total (*confirm on install*).
  Tests prove that a timeout raises the timeout exception; they do not prove a total-time cap.
- **Rationale**: The SDK default is 10 minutes, too long for an interactive service. 60 s is a
  starting point chosen by judgment, **not a measured value**; the manual real call (feature
  evidence) and the later evals feature should confirm or change it. Long replies on the newest
  models can take longer, which is exactly why it is a setting.
- **Risk, unverified**: The SDK may refuse non-streaming requests with a very large `max_tokens`
  (it asks for streaming to avoid HTTP timeouts). Streaming is out of scope; this feature does
  not cap `max_tokens`, and the manual call uses a small value. If a later feature needs large
  outputs, that feature must handle it.

## 7. Settings

- **Decision**: `LLMSettings(BaseSettings)` with `anthropic_api_key: SecretStr`, `llm_model: str`,
  `llm_timeout_seconds: float = 60`. Environment variable names are the field names in upper
  case: `ANTHROPIC_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`. `model_config` reads `.env` if
  present and ignores unknown variables (the file also holds `DATABASE_URL`).
- **No default model**: `LLM_MODEL` is required. Pinning a default would hide which model is in
  use and make evals ambiguous. The example file shows a value as a placeholder.
- **Settings are built on demand, not at import**: `LLMSettings()` is called by the adapter's
  `from_env()` constructor, never at module level. A missing or invalid value raises
  `LLMConfigurationError` whose message names the environment variable (for example
  "ANTHROPIC_API_KEY is not set"), built from the field name (FR-017), never from the raw input
  value (FR-016). `LLMConfigurationError` is deliberately **not** a subclass of `LLMError`: it is a
  setup mistake, not a provider failure, so code that catches `LLMError` around calls does not
  swallow it.
- **`SecretStr`**: its `repr` and `str` show `**********` (*confirm on install*); the adapter
  calls `get_secret_value()` once, to build the SDK client, and keeps no other copy.
- **Tests must ignore a developer's `.env`**: settings tests construct `LLMSettings(_env_file=None)`
  and use `monkeypatch` to set or remove variables.
- **Alternatives considered**: Reading `os.environ` by hand (rejected: loses validation and the
  secret type); letting the SDK read `ANTHROPIC_API_KEY` itself (rejected: the failure would be
  the SDK's, with its own wording, and at a different moment).

## 8. The fake client

- **Decision**: `FakeLLMClient` in `tests/fake_llm.py`, with a `fake_llm` fixture in
  `tests/conftest.py` that returns a fresh instance. Test modules import it with
  `from fake_llm import FakeLLMClient` (*confirm on install*: this relies on pytest putting
  `tests/` on `sys.path`, its default for a folder without `__init__.py`; if it does not work, add
  `tests` to `pythonpath` in `pyproject.toml`). It holds a queue of scripted items,
  each an `LLMResponse` or an `LLMError` instance, consumed in order by `complete`. It records
  every `LLMRequest` it receives in `calls`. Helpers: `will_return(...)`, `will_fail(error)`.
  An empty queue raises `FakeScriptExhaustedError`, which is **not** an `LLMError`, so code under
  test cannot swallow it by catching provider failures.
- **Why in `tests/`, not `src/`**: it is a test double, so it must not ship in the Docker image
  or be importable by production code. Later features' tests reuse it through the same import or
  the fixture. Cost: the fake itself needs a small test of its own (`tests/test_llm_fake.py`
  already covers this), and the real package does not offer a no-key mode for local runs.
- **Alternatives considered**: `unittest.mock.AsyncMock` (rejected: does not enforce the real
  contract, accepts anything).

## 9. Async tests without a new dependency

- **Decision**: Use the `anyio` pytest plugin, already installed as a dependency of Starlette
  (*confirm on install*), with `@pytest.mark.anyio` and an `anyio_backend` fixture fixed to
  `"asyncio"` in `tests/conftest.py` (trio is not installed). Fallback if the plugin is not
  active: `asyncio.run(...)` inside plain sync tests.
- **Alternatives considered**: Adding `pytest-asyncio` (rejected for now: a new dev dependency
  with no need).

## 10. New dependency: the Anthropic SDK

- **Decision**: Add `anthropic` (current major, resolved by `uv add anthropic`) as a runtime
  dependency. `pydantic-settings` is already declared in `pyproject.toml`; no new entry.
- **Justification (constitution, Technical Constraints)**: The official SDK provides the typed
  exception classes, the response models and the request handling that the adapter translates.
  Writing raw HTTP would mean re-implementing authentication headers, error classification and
  response parsing, with more risk and no benefit. The SDK is used only inside
  `anthropic_adapter.py`; nothing else imports it, so replacing it touches one file.
- **Alternatives considered**: Raw `httpx2` calls (rejected, above); a multi-provider library
  such as LiteLLM (rejected: a large dependency that the "one interface, our own adapters"
  design is meant to avoid).

## 11. Manual real call (evidence)

- **Decision**: A script `scripts/manual_anthropic_call.py` (outside `tests/`, so pytest never
  collects it and CI never runs it) builds the adapter from the environment, sends one short
  synthetic prompt with a small `max_tokens`, and prints text, usage, model and stop reason. The
  owner runs it once with their own key and pastes the output, plus date, into
  `docs/evidence/llm-client-anthropic.md`. The file contains no key. The script refuses to run if
  the `CI` environment variable is set.
- **Cost note**: One small call on the owner's key; cost is not calculated by this feature.
