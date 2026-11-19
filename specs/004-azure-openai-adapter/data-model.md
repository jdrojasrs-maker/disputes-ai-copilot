# Data Model: Azure OpenAI Adapter

No persisted data. The request and response types are the existing ones from feature 003
(`LLMRequest`, `Message`, `LLMResponse`, `TokenUsage`, `StopReason`) and are reused unchanged.

## AzureOpenAISettings (new, read from the environment when the adapter is built)

| Field | Environment variable | Rule | Notes |
|---|---|---|---|
| `azure_openai_base_url` | `AZURE_OPENAI_BASE_URL` | required; valid HTTP(S) URL | Azure v1 endpoint of the resource |
| `azure_openai_api_key` | `AZURE_OPENAI_API_KEY` | required; `SecretStr` | never printed, logged or in an error |
| `azure_openai_deployment` | `AZURE_OPENAI_DEPLOYMENT` | required; non-empty | the deployment name, not the model id |
| `llm_timeout_seconds` | `LLM_TIMEOUT_SECONDS` | optional; default 60; greater than 0 | shared with the Anthropic adapter; maximum wait per phase |

A missing or invalid value raises `LLMConfigurationError` naming the variable, built from the
variable name and the rule text, never from the supplied value.

## AzureOpenAILLMClient (new)

Holds only the deployment name and the SDK client. No conversation state. `repr` shows the
deployment and never the key. Built directly (key, base URL, deployment, timeout, optional HTTP
client for tests) or with `from_env()`.

## Mappings

Stop reason (provider `finish_reason` to neutral `StopReason`):

| Provider value | Neutral |
|---|---|
| `stop` | `completed` |
| `length` | `max_tokens` |
| `content_filter`, `tool_calls`, `function_call`, anything else | `other` |

Usage: `prompt_tokens` to `input_tokens`; `completion_tokens` to `output_tokens`. `total_tokens`
and reasoning-token details are not used.

No-text answer (no choices, `content` null or blank) or missing `usage`: raises the base
`LLMError`, not retryable.
