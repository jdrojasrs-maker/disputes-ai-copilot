# Evidence: one real call through the Anthropic adapter

This is the manual evidence for feature 003 (spec requirement FR-020). It records what actually
happened when the adapter was run by hand. It is **not** run in CI and no unit test calls a real
model.

- **Date**: 2026-11-17
- **Run by**: the project owner, on their own API key (a small cost on that key)
- **Command** (from the repository root, with `ANTHROPIC_API_KEY` and `LLM_MODEL` in a local
  `.env` file that is not versioned):

  ```text
  uv run python scripts/manual_anthropic_call.py
  ```

- **Prompt** (synthetic): system prompt "You help a card-disputes team. Answer in one short
  sentence."; one user message "In one sentence, what is a chargeback?"; `max_tokens` 1024.

## Result: successful call

Output of the script, copied as printed:

```text
Client:      AnthropicLLMClient(model='claude-sonnet-5-5')
System:      You help a card-disputes team. Answer in one short sentence.
Question:    In one sentence, what is a chargeback?
max_tokens:  1024
Answer:      A chargeback is a forced reversal of a card transaction, initiated by the cardholder's bank, that returns funds to the customer after they dispute the charge and is typically debited from the merchant.
Input tokens:  43
Output tokens: 63
Model:       claude-sonnet-5-5
Stop reason: completed
```

What this shows:

- The adapter was built from the environment, sent a request and returned a neutral response
  with text, input and output token counts, the model that answered and a stop reason.
- The provider's stop value was mapped to the neutral `completed`.
- The printed client (`repr`) shows the model and no key.

## Earlier attempt: wrong model name (observed failure)

Before the successful run, the same command was run while `LLM_MODEL` still held the placeholder
from `.env.example`. The provider answered with HTTP 404, and the adapter translated it:

```text
Client:      AnthropicLLMClient(model='replace-with-a-model-id')
Call failed:  LLMBadRequestError: Anthropic rejected the request (HTTP 404)
retryable:    False
status_code:  404
request_id:   req_011Ch9EYY31yqNmWJKG7yKtg
```

This is a real provider failure translated into the service's own exception: a
`LLMBadRequestError` that is not retryable, with the status code and the provider's request id,
and no key in the output. It also shows that the key was accepted (a bad key would have been a
401, which maps to `LLMAuthenticationError`).

## What this evidence does not show

- **Latency**: the script does not measure time, so no latency figure is claimed. The default
  call timeout of 60 seconds is therefore **not** validated by this call (research.md section 6).
- **Thinking tokens**: the answer was short and the output was 63 tokens. This call does not
  settle whether thinking tokens count against `max_tokens` (research.md section 3 keeps that
  point marked as unconfirmed).
- **Cost**: this feature does not calculate cost, and none is stated here.
- **Other failure kinds** (rate limit, timeout, provider unavailable, authentication): they are
  covered by unit tests against a simulated transport, not by real calls.
