# Evidence: one real call through the Azure OpenAI adapter

This is the manual evidence for feature 004 (spec requirement FR-020). It records what actually
happened when the adapter was run by hand. It is **not** run in CI and no unit test calls a real
model.

- **Date**: 2026-11-18
- **Run by**: the project owner, on their own Azure resource (a small cost on that resource)
- **Deployment**: `gpt-5.4-mini`, deployment type Global Standard (a chat model deployed in
  Microsoft Foundry)
- **Command** (from the repository root, with `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY` and
  `AZURE_OPENAI_DEPLOYMENT` in a local `.env` file that is not versioned):

  ```text
  uv run python scripts/manual_azure_openai_call.py
  ```

- **Prompt** (synthetic): system prompt "You help a card-disputes team. Answer in one short
  sentence."; one user message "In one sentence, what is a chargeback?"; `max_tokens` 1024, which
  the adapter sends as `max_completion_tokens`.

## Result: successful call

Output of the script, copied as printed:

```text
Client:      AzureOpenAILLMClient(deployment='gpt-5.4-mini')
System:      You help a card-disputes team. Answer in one short sentence.
Question:    In one sentence, what is a chargeback?
max_tokens:  1024 (sent as max_completion_tokens)
Answer:      A chargeback is a reversal of a card payment initiated by the cardholder’s bank, usually after a disputed or unauthorized transaction.
Input tokens:  35
Output tokens: 29
Model:       gpt-5.4-mini-2026-03-17
Stop reason: completed
```

What this shows:

- The adapter was built from the environment, sent a request and returned a neutral response
  with text, input and output token counts, the model that answered and a stop reason.
- The service accepted the system prompt sent as a message with the `system` role. This was an
  open question in the plan (research.md D3) and is now observed for this deployment.
- The service accepted `max_completion_tokens` (an earlier direct call had shown it rejects
  `max_tokens` with HTTP 400).
- The model name returned (`gpt-5.4-mini-2026-03-17`) is the versioned name the service reports;
  it differs from the deployment name (`gpt-5.4-mini`), as the adapter expects.
- The provider's `stop` value was mapped to the neutral `completed`.
- The printed client (`repr`) shows the deployment and no key.

## Earlier attempt: endpoint host did not resolve (observed failure)

Before the successful run, the script was run once with an endpoint setting that did not work:

```text
Client:      AzureOpenAILLMClient(deployment='gpt-5.4-mini')
Call failed:  LLMProviderUnavailableError: Could not connect to Azure OpenAI
retryable:    True
status_code:  None
request_id:   None
```

A separate name lookup (no request sent) showed that the host in the configured endpoint did not
resolve in DNS, while other hosts did. The adapter translated the connection failure into the
service's own `LLMProviderUnavailableError`, retryable, with no status code and no key in the
output. This is one real failure kind. It also shows a limit of the design: the adapter hides the
provider's cause on purpose (so that no key or provider text can leak), so the message alone does
not say that the cause was a wrong host name.

## What this evidence does not show

- **Latency**: the script does not measure time, so no latency figure is claimed. The default
  call timeout of 60 seconds is therefore **not** validated by this call.
- **Reasoning tokens**: the script prints only input and output tokens, and the answer was short
  (29 output tokens). This call does not show whether reasoning tokens are counted inside the
  completion tokens (research.md D4 keeps that point marked as unverified).
- **Cost**: this feature does not calculate cost, and none is stated here.
- **Other failure kinds** (authentication, bad request, rate limit, timeout, content-filter
  block, answer with no text): they are covered by unit tests against a simulated transport, not
  by real calls. Only the connection failure above was observed for real.
- **Other deployments or model families**: one deployment type and one model were used.
- **The v1 endpoint form**: the call used the Azure v1 endpoint with the OpenAI client class, as
  designed; other endpoint forms were not tried.
