# Data Model: LLM Client Abstraction

All types live in the new package `src/disputes/llm/`. All models are Pydantic v2 and frozen
(`model_config = ConfigDict(frozen=True, extra="forbid")`), so a value cannot change after it is
built and an unknown field is an error (FR-005, FR-007, FR-008).

## Role (enum)

`user`, `assistant`. Any other value is a validation error (FR-003).

## Message

| Field | Type | Rule |
|---|---|---|
| `role` | `Role` | one of the two values above |
| `content` | `str` | not empty after trimming whitespace (whitespace-only is rejected) |

The text is stored as given, not trimmed, so the client never alters what it is asked to send.

## LLMRequest

| Field | Type | Rule |
|---|---|---|
| `system` | `str \| None` | optional; default `None`. If given, not empty after trimming |
| `messages` | `tuple[Message, ...]` | at least one message (FR-004). No order rule (clarification 3) |
| `max_tokens` | `int` | greater than zero (FR-004) |

No sampling fields. A caller passing a list of messages gets it converted to a tuple; the
caller's list is never modified (FR-008).

## StopReason (enum)

`completed`, `max_tokens`, `other` (clarification 1). Mapping from the provider is in
research.md section 3.

## TokenUsage

| Field | Type | Rule |
|---|---|---|
| `input_tokens` | `int` | greater than or equal to zero |
| `output_tokens` | `int` | greater than or equal to zero |

## LLMResponse

| Field | Type | Rule |
|---|---|---|
| `text` | `str` | may be empty (answer with no text content, or cut off before any text) |
| `usage` | `TokenUsage` | |
| `model` | `str` | the model that answered, as reported by the provider; not empty |
| `stop_reason` | `StopReason` | |

Frozen: assigning to a field raises an error (spec story 1, scenario 6).

## Exceptions

```text
LLMError                       retryable = False   (base; anything else)
├── LLMAuthenticationError     retryable = False
├── LLMBadRequestError         retryable = False
├── LLMRateLimitError          retryable = True
├── LLMTimeoutError            retryable = True
└── LLMProviderUnavailableError retryable = True

LLMConfigurationError          (separate; not an LLMError) setup mistake, names the variable
FakeScriptExhaustedError       (separate; not an LLMError) defined in tests/fake_llm.py, script ran out
```

`retryable` is a class attribute, readable without an instance (FR-010). Every `LLMError` also
carries two optional attributes, `status_code: int | None` and `request_id: str | None`, set by
the adapter for diagnosis. The message never includes the key (FR-016).

## LLMSettings

| Field | Environment variable | Type | Rule |
|---|---|---|---|
| `anthropic_api_key` | `ANTHROPIC_API_KEY` | `SecretStr` | required; masked in `repr`/`str` |
| `llm_model` | `LLM_MODEL` | `str` | required; not empty |
| `llm_timeout_seconds` | `LLM_TIMEOUT_SECONDS` | `float` | greater than zero; default 60 |

## Relationships

`LLMClient.complete(LLMRequest) -> LLMResponse`, raising only `LLMError` subclasses for provider
failures. `FakeLLMClient` (in `tests/fake_llm.py`) and `AnthropicLLMClient` both satisfy
`LLMClient`. Only the adapter
reads `LLMSettings` and imports the provider SDK.
