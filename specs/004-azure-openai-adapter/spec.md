# Feature Specification: Azure OpenAI Adapter for the LLM Client

**Feature Branch**: `feat/004-azure-openai-adapter` (not yet created)

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "Azure OpenAI adapter for the LLM client. Add a second implementation of the existing LLMClient interface that calls a chat model deployed in Microsoft Foundry (Azure OpenAI), so the rest of the service can switch provider without changes. It accepts the same request as the Anthropic adapter and returns the same response. Observed behavior of the real service (manual call to a gpt-5.4-mini deployment, Global Standard, 2026-11-18): text in the first choice's message content; usage reports prompt, completion and total tokens, with reasoning tokens in a separate detail field; stop value was `stop`; the model field returned the versioned model name, which differs from the deployment name; the response carries content-filter results; the request's model field takes the deployment name; the service rejected `max_tokens` with HTTP 400 and requires `max_completion_tokens`. Provider failures are translated into the service's own error family, one attempt per call, a response with no text is handled explicitly. Settings (endpoint base URL, API key as a secret, deployment name) come from the environment and fail by name at build time, not at import. Shared behavior tests run against the fake, the Anthropic adapter and this adapter with simulated transport. One real call is documented manually as evidence. Out of scope: retries and backoff, streaming, tool use, structured output, sampling parameters, key-less (Entra) authentication, any HTTP endpoint using the client, caching and cost calculation."

> **Numbering note**: Spec Kit's sequential numbering assigns `004` to this directory. The
> roadmap in `CLAUDE.md` lists the Azure adapter as an unnumbered item and reserves "004" for
> `POST /disputes/intake`; the roadmap must be reconciled when this feature closes.

## Clarifications

### Session 2026-11-18

- Q: When Azure returns an answer with no text (content-filter block, no choices), should the adapter raise an error or return empty text? → A: Raise a service error. It is the existing base error (not retryable; no new error type), with a message written by the service. No empty-text response is ever returned.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask an Azure-hosted model through the same interface (Priority: P1)

A developer building a later feature has code that sends a request (optional system prompt,
validated messages, maximum output tokens) through the existing client interface. They build the
Azure adapter instead of the Anthropic one and send the same request. They get back the same
immutable response: generated text, token usage (input and output), the name of the model that
answered, and a provider-neutral stop reason. Nothing else in their code changes.

**Why this priority**: Switching provider without touching callers is the whole point of the
feature. It can be exercised completely with simulated transport, with no network and no key.

**Independent Test**: With the provider's transport simulated, send a request and confirm the
response carries the text from the first choice, input tokens from prompt tokens, output tokens
from completion tokens, the versioned model name the provider reported (not the deployment
name), and the neutral stop reason.

**Acceptance Scenarios**:

1. **Given** a request with a system prompt and one user message, **When** it is sent through
   the Azure adapter, **Then** the response has the generated text, input and output token
   counts, the model name reported by the provider and a stop reason.
2. **Given** a request without a system prompt, **When** it is sent, **Then** it is accepted and
   answered the same way.
3. **Given** a provider answer whose stop value is `stop`, **When** it is mapped, **Then** the
   neutral reason is "completed".
4. **Given** a provider answer whose stop value is the length limit, **When** it is mapped,
   **Then** the neutral reason is "hit token limit", the text produced so far is returned and no
   exception is raised.
5. **Given** any other provider stop value (for example, content filtered), **When** it is
   mapped, **Then** the neutral reason is "other".
6. **Given** the provider reports reasoning tokens in a separate detail field, **When** the
   usage is mapped, **Then** output tokens equal the provider's completion tokens, with no
   separate adjustment.
7. **Given** a request is sent, **When** the outgoing provider request is inspected, **Then** it
   carries the maximum output tokens as `max_completion_tokens`, does not carry `max_tokens`,
   names the deployment as the model, and carries no sampling parameters.
8. **Given** a request sent twice, **When** the second call is made, **Then** it does not depend
   on the first, and the messages passed in are never modified.

---

### User Story 2 - One shared behavior suite proves every implementation (Priority: P1)

A developer checks that any client implementation honors the same contract. One shared set of
behavior tests runs against the fake client, the Anthropic adapter and the Azure adapter, each
with simulated transport and no network. A new provider passes by satisfying the same tests,
not by adding provider-specific copies of them.

**Why this priority**: It is what makes "the rest of the service can switch provider without
changes" a checked claim instead of a hope, and it protects the Anthropic adapter from
regressions caused by this feature.

**Independent Test**: Run the shared suite and confirm it executes once per implementation (three
runs of each shared test), all passing, with no network access.

**Acceptance Scenarios**:

1. **Given** the shared suite, **When** it runs, **Then** each shared behavior is checked against
   the fake, the Anthropic adapter and the Azure adapter.
2. **Given** an implementation that returns a different shape or leaks a provider type, **When**
   the shared suite runs, **Then** it fails for that implementation.
3. **Given** the existing tests for features 001-003, **When** this feature is complete, **Then**
   they are unchanged and still pass.
4. **Given** any test in the suite, **When** it runs, **Then** no real model is called and no
   non-local network connection is attempted.

---

### User Story 3 - Handle Azure failures in the service's own vocabulary (Priority: P2)

A developer calling the Azure adapter handles failures with the service's own exceptions, the
same as for Anthropic: authentication, bad request, rate limit, timeout, provider unavailable,
and a base error for anything else. Each keeps its existing retryable flag. Messages are written
by the service and never include the key or the provider's raw error text. A response that has
no text is treated explicitly, not returned as an empty value.

**Why this priority**: Callers need stable failure handling regardless of provider, but it can
be validated after the happy path.

**Independent Test**: For each provider failure kind, simulate it and confirm the matching
service exception is raised, with the right retryable flag, one provider call only, and a
message free of the key and of the provider's text.

**Acceptance Scenarios**:

1. **Given** the provider rejects the credentials, **When** translated, **Then** an
   authentication error (not retryable) is raised.
2. **Given** the provider rejects the request as malformed, **When** translated, **Then** a
   bad-request error (not retryable) is raised.
3. **Given** the provider reports rate limiting, a timeout, or unavailability, **When**
   translated, **Then** the matching service exception is raised and marked retryable.
4. **Given** any other provider failure, **When** translated, **Then** the base error is raised.
5. **Given** any translated failure, **When** its message and its cause chain are inspected,
   **Then** neither contains the API key nor the provider's raw error text.
6. **Given** a provider that fails, **When** a request is sent, **Then** the provider is called
   once only (no automatic retry).
7. **Given** a provider answer with no text (for example, blocked by the provider's content
   filter, or no choices returned), **When** it is mapped, **Then** the base service error
   (not retryable) is raised with a service-written message, and no response with empty text is
   ever returned.

---

### User Story 4 - Configure the adapter safely from the environment (Priority: P2)

A developer sets the endpoint base URL, the API key and the deployment name in the environment,
builds the adapter, and sends a request. A missing or invalid setting fails with a clear error
naming the variable, when the adapter is built and never when the module is imported. The key is
held as a secret value and never printed, logged or included in an error. `.env.example`
documents the variables with placeholders only.

**Why this priority**: Required for safe real use, and independent of the mapping logic.

**Independent Test**: Build the adapter with each setting missing in turn and with an invalid
base URL, and confirm each failure names the variable; import the module with an empty
environment and confirm nothing fails; print the settings and confirm the key is masked.

**Acceptance Scenarios**:

1. **Given** valid settings, **When** the adapter is built, **Then** it is ready to send
   requests.
2. **Given** the key, the base URL or the deployment name is missing, **When** the adapter is
   built, **Then** it fails with an error naming that variable.
3. **Given** the base URL is not a valid URL, **When** the adapter is built, **Then** it fails
   with an error naming the base URL variable.
4. **Given** an empty environment, **When** the module is imported, **Then** nothing fails.
5. **Given** the settings are printed or logged, **When** the output is inspected, **Then** the
   key is masked and its value does not appear.
6. **Given** `.env.example`, **When** it is read, **Then** the Azure variables appear with
   placeholders only and no real value.

---

### User Story 5 - Document one real call as evidence (Priority: P3)

A maintainer runs a script once, by hand, against a real Azure deployment and records the result
in `docs/evidence/`. The document shows the request, the answer text, usage and model name with
no secret in it, and states honestly what it does not show.

**Why this priority**: It supports the README's claim that the adapter works against the real
service, but it is manual and not part of CI.

**Independent Test**: Read the evidence file: it names the script, the date and the deployment
type, contains no secret, and lists its limits (latency, cost, other failure kinds not
measured). Confirm CI does not run the script.

**Acceptance Scenarios**:

1. **Given** a real endpoint, key and deployment and the manual procedure, **When** the script
   is run, **Then** a real answer is returned and printed with usage and model name, without
   printing the key.
2. **Given** the evidence document, **When** it is read, **Then** it states what it does not
   show (latency, cost, failure kinds other than the one observed).
3. **Given** the CI workflow, **When** it runs, **Then** the script is not executed.

---

### Edge Cases

- The provider answers with an empty list of choices, or the first choice's content is empty or
  absent (content filter): raises the base service error (FR-010).
- The provider reports a stop value the service does not know: mapped to "other".
- The model name reported by the provider differs from the deployment name: the reported name is
  returned, since it shows what actually answered.
- A request fails because the provider's rejection text mentions a request field (as happened
  with the maximum-tokens field): the message is still written by the service, never copied.
- Settings are valid in format but point to a deployment that does not exist: surfaces as a
  provider failure at call time, not at build time.
- The Anthropic adapter returns empty text for an answer with no text while the Azure adapter
  raises (see Assumptions); the shared behavior suite deliberately leaves this case out.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Azure adapter MUST implement the existing client interface so that any caller
  written against it works with this adapter without changes.
- **FR-002**: It MUST accept the same request as the Anthropic adapter (optional system prompt,
  validated messages, maximum output tokens) and return the same immutable response type.
- **FR-003**: The response MUST carry the text from the first choice's message content, input
  tokens from the provider's prompt tokens, output tokens from its completion tokens, and the
  model name as reported by the provider (not the deployment name).
- **FR-004**: The stop reason MUST map as follows: provider `stop` to "completed", the
  provider's length-limit value to "hit token limit", anything else to "other". A response cut
  by the limit MUST be returned, not raised.
- **FR-005**: The outgoing provider request MUST send the maximum output tokens as
  `max_completion_tokens` and MUST NOT send `max_tokens`.
- **FR-006**: The outgoing request MUST identify the model by the configured deployment name and
  MUST NOT carry sampling parameters.
- **FR-007**: The adapter MUST keep no conversation state between calls and MUST NOT modify the
  messages it receives.
- **FR-008**: Provider failures MUST be translated into the service's existing error family
  (authentication, bad request, rate limit, timeout, provider unavailable, base error for
  anything else), each keeping its existing retryable flag.
- **FR-009**: Error messages MUST be written by the service. They MUST NOT include the API key
  or the provider's raw error text, and neither the error's cause chain nor its context MUST
  retain the request carrying the key.
- **FR-010**: A provider answer with no text (empty choices, empty or absent content, such as a
  content-filter block) or with no token usage MUST raise the existing base service error (not retryable), with a
  message written by the service that includes neither the key nor provider text. It MUST NOT
  return a response with empty text and MUST NOT surface as an unrelated crash. (A response
  without usage cannot fill the neutral usage record, so it is handled the same way.) This is covered
  by a test.
- **FR-011**: The adapter MUST make exactly one attempt per call; the provider SDK's automatic
  retries MUST be turned off.
- **FR-012**: Settings (endpoint base URL, API key, deployment name) MUST be read from the
  environment with Pydantic settings and never from the repository. The key MUST be a secret
  value, never printed, logged or included in an error.
- **FR-013**: A missing or invalid setting MUST fail with an error naming the variable, when the
  adapter is built and not when the module is imported.
- **FR-014**: The existing timeout setting MUST apply to the Azure adapter as the maximum wait
  per call, with the same meaning as for Anthropic.
- **FR-015**: `.env.example` MUST document the Azure variables with placeholders only.
- **FR-016**: The provider SDK MUST be imported only inside the adapter module.
- **FR-017**: One shared behavior suite MUST run against the fake client, the Anthropic adapter
  and the Azure adapter, with simulated transport and no network.
- **FR-018**: A test MUST assert FR-005 (the request carries `max_completion_tokens` and not
  `max_tokens`).
- **FR-019**: Unit tests MUST NOT call a real model. The existing tests for features 001-003
  MUST NOT be modified.
- **FR-020**: One real call MUST be documented manually under `docs/evidence/` with a script
  under `scripts/`, not run in CI, and the document MUST state what it does not show (latency,
  cost, other failure kinds).
- **FR-021**: The feature MUST NOT add retries, backoff, streaming, tool use, structured output,
  sampling parameters, key-less (Microsoft Entra) authentication, any HTTP endpoint using the
  client, caching or cost calculation.

### Key Entities

- **Azure adapter**: A client implementation bound to one endpoint and one deployment; stateless
  between calls.
- **Azure settings**: Endpoint base URL, API key (secret) and deployment name, plus the shared
  timeout; read from the environment when the adapter is built.
- **Provider answer**: What the real service returns (text, usage, versioned model name, stop
  value, content-filter results); only text, usage, model name and stop value are used.
- **Neutral response and stop reason**: The existing provider-independent result and its three
  reasons (completed, hit token limit, other).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A caller written against the interface switches between the Anthropic and Azure
  providers by changing only which adapter is built: zero changes in caller code (for the success
  path and every failure kind; the no-text case is the documented exception).
- **SC-002**: The shared behavior suite passes for 3 of 3 implementations (fake, Anthropic,
  Azure) with no network access.
- **SC-003**: Each of the 6 failure kinds is raised as the correct service exception with the
  correct retryable flag for the Azure adapter, and in 100% of those cases the message contains
  neither the key nor provider text.
- **SC-004**: A failing call produces exactly 1 provider attempt, never more.
- **SC-005**: Building the adapter with any one of the 3 settings missing fails 3 of 3 times with
  an error naming that variable; importing the module with an empty environment never fails.
- **SC-006**: The tests from features 001-003 pass unmodified; the full suite and lint are green
  in CI.
- **SC-007**: The evidence document records one real answer, with text, usage and model name, and
  contains no secret.

## Assumptions

- In the no-text case the two adapters differ on purpose for now: the Anthropic adapter (feature
  003, whose tests are not modified) returns empty text, the Azure adapter raises the base error.
  Callers that must handle both providers identically in that case are not yet served; reconciling
  them needs a later feature allowed to touch 003. SC-001 (no caller code changes) therefore holds
  for the success path and for every failure kind, not for this one case.
- The request and response types, the error family and the shared timeout setting from feature
  003 are reused as they are; this feature adds no new error types or request fields.
- The real service behaviors in the input (field names, `max_completion_tokens`, versioned model
  name, usage fields, stop value `stop`) were observed in one manual call on 2026-11-18 to a
  gpt-5.4-mini Global Standard deployment. Other behaviors (the exact length-limit stop value,
  the shape of a content-filter block, error shapes) are taken from the SDK's documentation and
  MUST be verified in the plan, and are marked as unverified until then.
- Reasoning tokens are already counted inside completion tokens, so output tokens are not
  adjusted. This is to be confirmed in the plan against the provider's documentation.
- The Azure variables use the same naming style as the existing Anthropic ones; exact names are
  decided in the plan.
- The caller's deployment is a chat model reachable with key authentication; Microsoft Entra
  authentication is out of scope.
- No endpoint uses the client yet, so this feature changes no HTTP behavior.
- The new SDK dependency requires a justification in the plan (Technical Constraints).
- Tests stay few and explainable (constitution v2.0.0, Principle I): the shared suite is
  parameterized over three implementations, so the plan states the resulting test count, and
  a count above about 15 is justified in one line.
