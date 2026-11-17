# Feature Specification: LLM Client Abstraction

**Feature Branch**: `feat/003-llm-client` (specs drafted on `docs/spec-kit-003-llm-client`)

**Created**: 2026-11-17

**Status**: Draft

**Input**: User description: "LLM client abstraction. The service needs one internal async interface to talk to a language model, so the rest of the code never depends on a specific provider. A call takes an optional system prompt, a list of conversation messages (validated: role is user or assistant, text is not empty) and a maximum number of output tokens. It does not expose sampling parameters (temperature, top_p, top_k): current Claude models reject them. It returns an immutable response with the generated text, the token usage (input and output tokens) and the name of the model that answered. Messages and responses are Pydantic models. The interface keeps no conversation state and never modifies the messages it receives. Provider failures are translated into the service's own exceptions: authentication, bad request, rate limit, timeout, provider unavailable, and a base error for anything else; each one declares whether it is retryable, so a later feature can add retries without changing them. Pieces: (1) the interface; (2) a fake client for tests that returns scripted answers, records the calls it received and can simulate each failure, with no network access; (3) an Anthropic adapter, configured with the SDK's own automatic retries explicitly turned off, so no hidden retry happens until a deliberate one is designed. Settings (API key and model name) are read from the environment with Pydantic settings, never from the repository; the key is held as a secret value, never printed, logged or included in an error message; a missing key fails with a clear error naming the variable when the adapter is built, not when the module is imported. A .env.example with placeholders documents the variables. Unit tests never call a real model. One real call to the Anthropic API is documented manually, not run in CI, as evidence. Out of scope: retries and backoff (deferred to a later feature), Azure OpenAI adapter (separate feature), streaming, tool use, structured output, sampling parameters, any HTTP endpoint that uses the client, caching and cost calculation."

## Clarifications

### Session 2026-11-17

- Q: When the model stops because it hit the maximum output tokens, should the response say so, or return only the text? → A: The response includes a provider-neutral stop reason (finished normally, hit token limit, other). Hitting the limit is returned, not raised as an error.
- Q: How long should a single model call wait before the adapter raises the timeout error? → A: A timeout setting read from the environment alongside the key and model name, with a documented default in `.env.example`.
- Q: Should the client reject a conversation whose turns are in an odd order, or leave that to the provider? → A: The client does not check order; only non-empty list, valid roles and non-empty text are validated. The provider's rejection is translated into a bad-request error.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a model through one provider-neutral interface (Priority: P1)

A developer building a later feature (intake, RAG, agent) needs to ask a language model a
question. They build a request from an optional system prompt, a list of conversation messages
and a maximum number of output tokens, send it through the single client interface, and get back
an immutable response: the generated text, the token usage (input and output), the name of
the model that answered and why it stopped. Nothing in their code names a provider.

**Why this priority**: This is the contract every later AI feature depends on. Without it
there is nothing to build on, and it can be exercised completely with the fake client, with no
network and no key.

**Independent Test**: Build requests and responses and confirm that invalid ones are rejected,
that a response cannot be changed, and that the messages passed in are unchanged. Sending a
request through the fake client (User Story 2) then shows the scripted text, usage, model name and
stop reason coming back.

**Acceptance Scenarios**:

1. **Given** a request with a system prompt, one user message and a token limit, **When** it is
   sent through the client, **Then** the response contains the generated text, the input and
   output token counts, the model name and the stop reason.
2. **Given** a model answer that was cut off by the token limit, **When** it is returned,
   **Then** the response carries the text produced so far with the stop reason "hit token
   limit", and no exception is raised.
3. **Given** a request without a system prompt, **When** it is sent, **Then** it is accepted and
   answered the same way.
4. **Given** a message with a role other than user or assistant, or with empty text, **When**
   the message is built, **Then** it is rejected with a validation error and no call is made.
5. **Given** a request that is sent twice, **When** the second call is made, **Then** it does
   not depend on or reveal anything from the first (the client keeps no conversation state), and
   the messages passed in are never modified.
6. **Given** a response that was returned, **When** a caller tries to change one of its fields,
   **Then** the change is refused.

---

### User Story 2 - Test code that uses the client without a network (Priority: P1)

A developer writing tests for a later feature uses a fake client that returns answers they
scripted in advance, records every request it received, and can be told to fail in any of the
service's failure ways. Their unit tests never reach a real model, need no key and cost nothing.

**Why this priority**: The project rule is that unit tests never call a real model. The fake
is the only way later features can be tested at all, so it is available to the tests together
with the interface (it lives with the tests and is not part of the shipped service).

**Independent Test**: Script two answers and one failure on the fake, make three calls, and
confirm the answers come back in order, the failure is raised on the third, and the recorded
requests match what was sent.

**Acceptance Scenarios**:

1. **Given** a fake scripted with an answer, **When** a request is sent, **Then** that answer is
   returned and the request is recorded for later inspection.
2. **Given** a fake scripted to simulate each failure kind (authentication, bad request, rate
   limit, timeout, provider unavailable, other), **When** a request is sent, **Then** the
   corresponding service exception is raised.
3. **Given** a fake with nothing left in its script, **When** a request is sent, **Then** it
   fails with a clear error instead of inventing an answer.
4. **Given** any test using the fake, **When** it runs, **Then** it makes no network access.

---

### User Story 3 - Handle provider failures in one vocabulary, ready for retries (Priority: P2)

A developer calling the client handles failures using the service's own exceptions, never a
provider's. There is one exception for each of: authentication, bad request, rate limit,
timeout, provider unavailable, and a base error for anything else. Each declares whether it is
retryable, so a later feature can add retry and backoff by reading that flag, without changing
the exceptions or the adapters.

**Why this priority**: Callers need stable failure handling before real calls exist, but it can
be validated with the fake before the real adapter is complete.

**Independent Test**: For each exception kind, confirm it is a subclass of the base error and
that its retryable flag has the intended value (rate limit, timeout and provider unavailable
are retryable; authentication and bad request are not).

**Acceptance Scenarios**:

1. **Given** a provider authentication failure, **When** the adapter translates it, **Then** an
   authentication error that is not retryable is raised.
2. **Given** a provider rate-limit, timeout or unavailable failure, **When** translated,
   **Then** the matching service exception is raised and is marked retryable.
3. **Given** a provider rejection of the request as malformed, **When** translated, **Then** a
   bad-request error that is not retryable is raised.
4. **Given** any other provider failure, **When** translated, **Then** the base error is
   raised, and the original provider error is not exposed as the thing callers must catch.
5. **Given** any translated failure, **When** its message is inspected, **Then** it does not
   contain the API key.

---

### User Story 4 - Call Anthropic safely through the adapter (Priority: P2)

A developer configures the service with an API key and a model name taken from the environment,
builds the Anthropic adapter, and sends a request. The adapter makes exactly one attempt per
call: the provider SDK's own automatic retries are explicitly turned off, so no retry happens
until a deliberate one is designed. The key is held as a secret value and never appears in
output, logs or error messages.

**Why this priority**: This is the first real connection to a model, but it depends on the
interface, failures and settings being in place, and it is validated by one manual real call
rather than by CI.

**Independent Test**: With the provider's client replaced by a stand-in, confirm the adapter
passes the request through, maps the answer to the neutral response, makes one attempt on
failure, and never reveals the key. Separately, run one real call manually and record it.

**Acceptance Scenarios**:

1. **Given** valid settings, **When** the adapter is built and a request is sent, **Then** the
   neutral response is returned with text, usage, model name and stop reason filled from the
   provider answer (the provider's own stop values are mapped to the neutral ones).
2. **Given** a provider that fails, **When** a request is sent, **Then** the provider is called
   once only and the translated exception is raised.
3. **Given** a configured timeout, **When** the provider does not answer within it, **Then**
   the timeout exception (retryable) is raised and the provider is not called again.
4. **Given** the key is missing from the environment, **When** the adapter is built, **Then**
   it fails with a clear error naming the missing variable.
5. **Given** the key is missing from the environment, **When** the module is merely imported,
   **Then** nothing fails.
6. **Given** settings are printed or logged, **When** the output is inspected, **Then** the key
   is masked and its value does not appear.
7. **Given** a real key and the manual procedure, **When** one real call is made, **Then** a
   real answer is returned and the evidence (request, answer text, usage, model name) is
   documented in the repository with no secret in it.

---

### Edge Cases

- Message list is empty: the request is rejected as invalid before any call.
- Message text is only whitespace: treated as empty and rejected.
- Maximum output tokens is zero or negative: rejected as invalid.
- System prompt is an empty or whitespace-only string: rejected as invalid; callers omit it
  instead.
- The conversation does not start with a user message, or roles do not alternate: the client does
  not check order; the provider's own rejection is translated into a bad-request error.
- The answer is cut off by the token limit: the response is returned with the text produced so
  far and the stop reason "hit token limit"; it is not an error.
- The provider answers with no text content: the response is still returned with empty text and
  the adapter does not invent text.
- The provider reports a failure whose message includes request data: the key is never part of
  any message the service raises.
- Two concurrent calls through the same client: neither affects the other, because no state is
  shared between calls.
- The fake is called more times than it has scripted answers: it fails clearly.
- The settings file (`.env`) is absent: values come from the real environment; only a missing
  required value is an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose one asynchronous client interface through which the rest
  of the service asks a language model, with no provider-specific types in its signature.
- **FR-002**: A call MUST accept an optional system prompt, a list of conversation messages and
  a maximum number of output tokens.
- **FR-003**: Each message MUST have a role limited to user or assistant and non-empty text
  (whitespace-only text counts as empty); an invalid message MUST be rejected at construction.
- **FR-004**: The maximum number of output tokens MUST be a positive integer; the message list
  MUST NOT be empty; a system prompt, when given, MUST NOT be empty or whitespace-only (omit it
  instead). Violations MUST be rejected before any call.
- **FR-005**: The interface MUST NOT accept sampling parameters (temperature, top_p, top_k).
- **FR-006**: A call MUST return an immutable response containing the generated text, the
  token usage (input tokens and output tokens), the name of the model that answered and a
  provider-neutral stop reason with exactly three values: `completed` (finished normally),
  `max_tokens` (hit the token limit) and `other`. Hitting the token limit MUST be returned as a normal response, not raised as an error.
- **FR-007**: Messages, requests and responses MUST be validated data models.
- **FR-008**: The client MUST keep no conversation state between calls and MUST NOT modify the
  messages it receives.
- **FR-009**: Provider failures MUST be translated into the service's own exceptions:
  authentication, bad request, rate limit, timeout, provider unavailable, and a base error for
  any other failure. All specific kinds MUST be subclasses of the base error.
- **FR-010**: Each service exception MUST declare whether it is retryable: rate limit, timeout
  and provider unavailable are retryable; authentication and bad request are not; the base
  error is not retryable by default.
- **FR-011**: A fake client MUST be provided that returns scripted answers in order, records
  every request it receives, can raise each of the service exceptions on demand, fails clearly
  when its script is exhausted, and performs no network access.
- **FR-012**: An Anthropic adapter MUST implement the interface and translate the provider's
  answer into the neutral response and the provider's failures into the service exceptions.
- **FR-013**: The Anthropic adapter MUST make exactly one provider attempt per call, with the
  provider SDK's automatic retries explicitly disabled. No retry or backoff exists in this
  feature.
- **FR-014**: Settings (API key, model name and call timeout in seconds) MUST be read from the
  environment, never from committed files. The key MUST be held as a secret value. The timeout
  MUST be a positive number with a documented default; an invalid value MUST fail when the
  settings are loaded.
- **FR-015**: The adapter MUST apply the timeout setting, in seconds, to every call as the
  maximum wait for each phase of the HTTP exchange (connecting, sending, waiting for the answer);
  when it is exceeded, the timeout service exception MUST be raised. It is not a guaranteed cap
  on the total duration of a call.
- **FR-016**: The API key MUST NOT appear in printed settings, logs, string forms of objects or
  any exception message.
- **FR-017**: A missing API key MUST fail with a clear error that names the variable, at the
  moment the adapter is built, and MUST NOT fail when the module is imported.
- **FR-018**: A `.env.example` file MUST document every variable with placeholders only, and
  real `.env` files MUST NOT be versioned.
- **FR-019**: Unit tests MUST NOT call a real model or the network. They use the fake, or a
  stand-in for the provider's client.
- **FR-020**: One real call to the Anthropic API MUST be performed manually, documented as
  evidence (procedure and result, without secrets), and MUST NOT run in CI.
- **FR-021**: The feature MUST NOT include a second provider, streaming, tool use, structured
  output, an HTTP endpoint using the client, caching, or cost calculation (retries and backoff
  are excluded by FR-013).

### Key Entities

- **Message**: One turn of a conversation. Role (user or assistant) and non-empty text.
- **Request**: What a call carries: optional system prompt, an ordered non-empty list of
  messages, and a positive maximum of output tokens.
- **Response**: Immutable result: generated text, token usage, the answering model's name and a
  stop reason (finished normally, hit token limit, other).
- **Token usage**: Input tokens and output tokens counted for one call.
- **Service exceptions**: A base error and five specific kinds (authentication, bad request,
  rate limit, timeout, provider unavailable), each with a retryable flag.
- **Client interface**: The single async contract; implemented by the fake and the Anthropic
  adapter (and later by other providers).
- **Settings**: API key (secret), model name and call timeout, read from the environment.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can write a test for a feature that uses a language model with only
  the fake: zero network access, zero key, and the test is deterministic across 100 repeated
  runs.
- **SC-002**: 100% of the service's failure kinds (six) have a test showing the exception raised
  and its retryable flag.
- **SC-003**: Across all unit tests and the full test suite in CI, 0 real model calls are made
  and 0 secrets are needed.
- **SC-004**: In every test that prints or logs settings and raises failures, the key value
  appears 0 times in the output.
- **SC-005**: When a provider call fails, the provider is called exactly once (0 hidden retries).
- **SC-006**: Importing the service with no key configured succeeds; building the adapter with
  no key fails with an error that names the missing variable, in 100% of tested cases.
- **SC-007**: One real call is documented with the actual returned text, token counts and model
  name, reproducible by following the written procedure.
- **SC-008**: Swapping the fake for the Anthropic adapter in a caller requires zero changes to
  the caller's code beyond choosing which client to build.

## Assumptions

- This feature is for developers of the service (internal contract), not end users; "users"
  above are those developers.
- Current Claude models reject sampling parameters (temperature, top_p, top_k). This was checked
  on 2026-11-17 against the Claude API reference bundled with the development tooling, not
  against the live official documentation page; it is recorded in research.md section 2.
- The environment variable for the key is `ANTHROPIC_API_KEY`, the provider's standard name; the
  names of the model and timeout variables, whether the model has a default, and the timeout's
  default value are decided in the plan. No model
  identifier is hard-coded into the adapter logic.
- Retry and backoff will be a later, deliberate feature that reads the retryable flag; nothing
  here prepares more than the flag.
- The Azure OpenAI adapter (separate feature) will implement the same interface; the interface
  must not need to change for it.
- Adding the provider SDK and the settings library as dependencies requires a justification in
  the plan (constitution: Technical Constraints).
- Test data and the manual real call use only synthetic content (constitution III); the manual
  real call incurs a small cost on the owner's own key.
- The manual evidence is stored in the repository documentation, not in test code.
- This feature adds no HTTP endpoint; the existing API is unchanged.
