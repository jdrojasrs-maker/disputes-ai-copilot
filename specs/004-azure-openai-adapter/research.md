# Research: Azure OpenAI Adapter

Method: observed facts come from the manual call of 2026-11-18 (gpt-5.4-mini, Global Standard).
SDK facts were read from the installed `openai` 3.55.1 package source in a scratch virtual
environment (Python 3.12), not from memory. Anything neither observed nor read is labeled
**Unverified**.

## D1: Which SDK class and endpoint style

- **Decision**: `openai.AsyncOpenAI(base_url=<endpoint>, api_key=..., max_retries=0, timeout=..., http_client=...)`, pointed at the Azure v1 endpoint. Not `AzureOpenAI`.
- **Rationale**: the manual call used `OpenAI(base_url=...)` and worked, so this is the observed path. `AsyncOpenAI.__init__` takes `max_retries` (default 2, so it must be set to 0), `timeout` and `http_client` (verified in the package signature).
- **Alternatives**: `AsyncAzureOpenAI` (needs an `api_version` and a different URL form; not what was observed).

## D2: Dependency

- **Decision**: add `openai>=3.55`. It depends on `httpx2`, as `anthropic` and the tests already do, so tests keep using `httpx2.MockTransport`.
- **Installed**: `openai 3.55.1` (T003).
- **Verified**: `openai` 3.55.1 requires `httpx2<3,>=2.12.0` (package metadata).

## D3: Outgoing request

- **Decision**: `chat.completions.create(model=<deployment>, messages=[...], max_completion_tokens=request.max_tokens)`; the system prompt becomes a first message with role `system`; no sampling parameters.
- **Observed**: the service rejected `max_tokens` (HTTP 400) and wants `max_completion_tokens`; the model field takes the deployment name.
- **Verified in SDK**: `create` accepts both parameters, so a test must assert the wire body (FR-018).
- **Verified (manual call, 2026-11-18)**: the `gpt-5.4-mini` deployment accepts the `system` role.

## D4: Response mapping

- **Verified in SDK types**: `choices[i].message.content` is `Optional[str]`; `finish_reason` is one of `stop`, `length`, `tool_calls`, `content_filter`, `function_call`; `usage` is `Optional[CompletionUsage]` with `prompt_tokens`, `completion_tokens`, `total_tokens` and optional `completion_tokens_details.reasoning_tokens`; `model` is `str`.
- **Decision**: text from `choices[0].message.content`; input tokens from `prompt_tokens`; output tokens from `completion_tokens`; model from the answer's `model`; `stop` to completed, `length` to max tokens, everything else (including `content_filter`, `tool_calls`) to other.
- **Observed**: `stop` and the versioned model name that differs from the deployment name; reasoning tokens were 0.
- **Reasoning tokens**: output tokens are not adjusted. The SDK docstring says prediction tokens "like reasoning tokens ... are still counted in the total completion tokens", which supports reasoning tokens being inside `completion_tokens`. That is a hint, not a statement of the Azure API; with reasoning tokens at 0 in the observed call, this is **Unverified** for a reasoning-heavy call and is listed as a limit in the evidence.
- **Missing `usage`** (the type allows it): treated as the same failure as no text, raising the base `LLMError`, since a response without usage cannot fill `TokenUsage`. Now part of FR-010 and covered by test 7.

## D5: No-text answer

- **Decision** (clarified with the owner): raise the base `LLMError` (not retryable) with a service-written message. Triggers: no choices, `content` null or empty after trimming.
- **Consequence**: the Anthropic adapter's existing, tested behavior is to return empty text in the same situation (`test_an_answer_with_no_text_gives_empty_text`). Feature 003 tests must not be modified, so the two adapters differ here. The shared suite therefore does not include the no-text case; it is tested only for Azure. This inconsistency is recorded as a known limit, to be reconciled in a later feature that is allowed to touch 003.

## D6: Error translation

- **Verified in SDK**: `APITimeoutError` is a subclass of `APIConnectionError` (test timeout first). Status errors: 400 `BadRequestError`, 401 `AuthenticationError`, 403 `PermissionDeniedError`, 404 `NotFoundError`, 409 `ConflictError`, 422 `UnprocessableEntityError`, 429 `RateLimitError`, 500 and above `InternalServerError`; **any other status (including 408) is a plain `APIStatusError`**. Unlike `anthropic`, there is no `RequestTimeoutError` class.
- **Decision**: same table as the Anthropic adapter: timeout and 408 (checked by `status_code == 408` on a plain `APIStatusError`) to `LLMTimeoutError`; connection to `LLMProviderUnavailableError`; 401 and 403 to authentication; 400, 404 and 422 to bad request; 429 to rate limit; 5xx to provider unavailable; the rest, including 409 and 418, to base `LLMError`. Messages are service text plus HTTP status; `request_id` is taken from the SDK error. Never `str(error)`. Raised outside the `except` block.
- **Verified in SDK**: `APIError` carries `request_id` read from the `x-request-id` header.
- **Unverified**: the exact error body Azure sends for a content-filtered *prompt*. It may arrive as HTTP 400 (then it is a bad-request error, which is acceptable) rather than as a 200 with `content_filter`. Not exercised in the manual call.

## D7: Settings

- **Decision**: new `AzureOpenAISettings` in `settings.py`: `azure_openai_base_url` (HTTP(S) URL), `azure_openai_api_key` (`SecretStr`), `azure_openai_deployment` (non-empty), `llm_timeout_seconds` (default 60, greater than 0, same variable as Anthropic). `load_azure_settings` reuses the same error-building logic as `load_settings` so messages name the variable and never include the supplied value. Variable names follow the manual script.
- **Rationale**: a separate class, because `LLMSettings` requires `ANTHROPIC_API_KEY` and `LLM_MODEL`, which an Azure-only setup does not have. `LLM_MODEL` is not used by this adapter (the deployment is the model name).

## D8: Shared behavior suite

- **Decision**: a small harness (`tests/llm_harness.py`) exposes, per implementation, a client plus two operations: "next answer is (text, usage, model, stop)" and "next call fails with kind K". The fake uses `will_return`/`will_fail`; the adapters use `httpx2.MockTransport` handlers with each provider's wire format. `test_llm_contract.py` is parameterized over the three harnesses. `tests/fake_llm.py` and the Anthropic test file are not edited.

## D9: Manual evidence

- **Decision**: `scripts/manual_azure_openai_call.py` builds the adapter from the environment, sends one request, prints text, usage, model and stop reason, never the key. It replaces the untracked scratch `scripts/first_azure_call.py` (which dumps the raw response JSON and loads `.env` with an undeclared `python-dotenv`; the owner decides whether to keep or delete it). The evidence document states what it does not show: latency, cost, failure kinds other than those actually observed, reasoning-heavy answers, content-filter blocks.
- CI does not run the script (it is not under `tests/`, and the workflow only runs `pytest` and `ruff`).
