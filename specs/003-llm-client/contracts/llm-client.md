# Contract: `LLMClient` (internal Python interface)

This service exposes no HTTP endpoint in this feature. The contract that later features depend on
is this Python interface. Types are in [data-model.md](../data-model.md).

## Interface

```python
class LLMClient(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
```

## Guarantees for callers

1. `complete` returns an `LLMResponse` or raises a subclass of `LLMError`. It raises nothing from
   the provider SDK.
2. It keeps no state between calls. Two calls with the same request do not depend on each other.
3. It does not modify `request` or its messages (they are immutable).
4. A cut-off answer (`stop_reason == max_tokens`) is a normal return, not an exception.
5. It makes at most one provider attempt per call. No retry, no backoff.
6. No exception message, `repr` or `str` of any object in this package contains the API key.

## Exceptions

| Exception | `retryable` | Raised when |
|---|---|---|
| `LLMAuthenticationError` | `False` | key rejected or not permitted |
| `LLMBadRequestError` | `False` | provider rejects the request (malformed, odd turn order, unknown model) |
| `LLMRateLimitError` | `True` | provider rate limit |
| `LLMTimeoutError` | `True` | no answer within `LLM_TIMEOUT_SECONDS` (per phase), or the provider answers 408 |
| `LLMProviderUnavailableError` | `True` | provider error (5xx, overloaded) or connection failure |
| `LLMError` | `False` | any other provider failure |

A later retry feature reads `exc.retryable` and needs no other change.

## Building a client

| Need | How |
|---|---|
| Tests | `from fake_llm import FakeLLMClient` (in `tests/`) or the `fake_llm` fixture, then `will_return(...)` / `will_fail(...)`; inspect `.calls` |
| Real Anthropic | `AnthropicLLMClient.from_env()` reads `ANTHROPIC_API_KEY`, `LLM_MODEL`, `LLM_TIMEOUT_SECONDS`; raises `LLMConfigurationError` naming the missing variable |

Swapping one for the other changes only the line that builds the client (SC-008).

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | none | secret; never printed or logged |
| `LLM_MODEL` | yes | none | model identifier sent to the provider |
| `LLM_TIMEOUT_SECONDS` | no | `60` | positive number |

Documented in `.env.example` with placeholders only.
