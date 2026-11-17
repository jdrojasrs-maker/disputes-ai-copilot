# Quickstart: validating the LLM client

Prerequisites: `uv sync` done. No API key is needed for the first two parts.

## 1. Unit tests (no network, no key)

```bash
uv run pytest tests/test_llm_models.py tests/test_llm_client_protocol.py tests/test_llm_errors.py \
  tests/test_llm_fake.py tests/test_llm_settings.py tests/test_llm_anthropic_adapter.py \
  tests/test_network_guard.py
uv run pytest        # whole suite, same as CI
uv run ruff check .
```

Expected: all pass, with `ANTHROPIC_API_KEY` unset. The adapter tests use a mock HTTP transport,
so even the real SDK never reaches the network.

## 2. Use the fake in a caller's test

Script an answer and a failure, call `complete` twice, and check `fake.calls` holds both requests
in order. See [contracts/llm-client.md](contracts/llm-client.md) for the methods.

## 3. Configuration errors

With the key unset, `AnthropicLLMClient.from_env()` must raise `LLMConfigurationError` whose
message names `ANTHROPIC_API_KEY` (and `LLM_MODEL` if that is also missing), while `import disputes.llm.anthropic_adapter` must succeed.

## 4. One real call (manual, not in CI, costs a small amount on your key)

1. Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY` and `LLM_MODEL` (the file is
   ignored by git).
2. Run `uv run python scripts/manual_anthropic_call.py`.
3. Expected: the script prints the answer text, input and output token counts, the model name and
   the stop reason, then exits 0. With a wrong key it prints an authentication error without the
   key.
4. Paste the output and the date into `docs/evidence/llm-client-anthropic.md`. Check that the file
   contains no key before committing.
