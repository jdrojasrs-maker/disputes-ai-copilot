# Contract: Azure OpenAI adapter

The adapter exposes no HTTP endpoint. Its contract is the existing `LLMClient` interface
(`async complete(LLMRequest) -> LLMResponse`) plus the provider-facing behavior below.

## Outgoing request (what the test in FR-018 asserts)

Chat completions call with this body:

```text
model                   = <deployment name>
messages                = [ {role: system, content: <system>}   (only when a system prompt exists)
                            {role: user|assistant, content: <text>} ... ]
max_completion_tokens   = <request.max_tokens>
```

Not present: `max_tokens`, `temperature`, `top_p`, `top_k`, `stream`, `tools`, `response_format`.
Credentials travel as the SDK's standard bearer header (to be observed in the test, as was done
for Anthropic). SDK client: `max_retries=0`, `timeout=<LLM_TIMEOUT_SECONDS>`.

## Response mapping

| Provider field | Neutral field |
|---|---|
| `choices[0].message.content` | `text` |
| `usage.prompt_tokens` | `usage.input_tokens` |
| `usage.completion_tokens` | `usage.output_tokens` |
| `model` (versioned name reported by the service) | `model` |
| `choices[0].finish_reason` | `stop_reason` (table in data-model.md) |

## Failure translation

| Provider failure | Service error | `retryable` |
|---|---|---|
| timeout (`APITimeoutError`) or HTTP 408 | `LLMTimeoutError` | yes |
| connection failure | `LLMProviderUnavailableError` | yes |
| HTTP 401, 403 | `LLMAuthenticationError` | no |
| HTTP 400, 404, 422 | `LLMBadRequestError` | no |
| HTTP 429 | `LLMRateLimitError` | yes |
| HTTP 5xx | `LLMProviderUnavailableError` | yes |
| any other status (e.g. 409, 418) | `LLMError` | no |
| answer with no text or no usage | `LLMError` | no |

Messages are service-written text plus the HTTP status. They never contain the key or the
provider's error text. `status_code` and `request_id` are set when the provider gave them. The
provider error is not attached as `__cause__` or `__context__`.

## Configuration

`AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, optional
`LLM_TIMEOUT_SECONDS`. Failure: `LLMConfigurationError` naming the variable, at build time.
