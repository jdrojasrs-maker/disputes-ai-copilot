# Quickstart: validating the Azure OpenAI adapter

## Prerequisites

- `uv sync` (after the `openai` dependency is added).
- For the manual call only: an Azure resource with a chat deployment, and in your local `.env`
  (never committed) `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`.

## 1. Automated checks (no network, no key)

```text
uv run pytest tests/test_llm_contract.py tests/test_llm_azure_adapter.py
uv run pytest
uv run ruff check .
```

Expected: the shared suite passes for the fake, the Anthropic adapter and the Azure adapter;
the full suite (including the existing tests from features 001-003, unmodified; their count is the one recorded in T001) and lint are
green. A test that tries a non-local connection fails loudly.

## 2. Switch provider without changing the caller

Build `AzureOpenAILLMClient.from_env()` where `AnthropicLLMClient.from_env()` was used and send
the same `LLMRequest`. Nothing else changes (SC-001). The shared suite proves this with a
caller written only against `LLMClient`.

## 3. Import and configuration behavior

With an empty environment (no `AZURE_*` variables), `import disputes.llm.azure_openai_adapter` succeeds;
`AzureOpenAILLMClient.from_env()` raises an error naming the first missing variable (SC-005).

## 4. One real call (manual, not in CI)

```text
uv run python scripts/manual_azure_openai_call.py
```

Expected: printed text, input and output tokens, the model name reported by the service (which
may differ from the deployment name), and the stop reason; no key in the output. Record the
output in `docs/evidence/llm-client-azure-openai.md` with the date, the deployment type, and the
limits (latency, cost, other failure kinds, reasoning-heavy answers, content-filter blocks not
shown). Also note whether the `system` role was accepted.
