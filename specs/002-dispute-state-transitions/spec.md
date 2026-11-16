# Feature Specification: Dispute State Transitions

**Feature Branch**: `feat/002-dispute-state-transitions`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "Dispute state transitions. Today a dispute is created in state "open" and can never change. Add the ability to move a dispute through its lifecycle. States: open, under_review, resolved, rejected, withdrawn. Allowed transitions: open -> under_review, under_review -> resolved, under_review -> rejected, and open -> withdrawn. The final states (resolved, rejected, withdrawn) are terminal: a closed dispute is never reopened. The full set of allowed transitions is defined in one place in the domain. A client requests a change with POST /disputes/{id}/transitions, sending the target state (to_state) and an optional note. On success the response returns the updated dispute. An unknown dispute id returns 404; an invalid body or unknown state returns 422; a transition that is not allowed from the current state returns 409. All errors use the existing single error format, and a rejected transition leaves the dispute unchanged. Each dispute records updated_at, refreshed on every successful transition, and keeps a history of its state changes (from state, to state, note, timestamp), readable through the API. Concurrency: if two incompatible transitions reach the same dispute at the same time (for example, resolve and reject), exactly one is applied and the other receives 409. A final state is never silently overwritten. This must be verified by a test that sends parallel requests. Also rename the reason "devolution" to "refund_not_received" in the dispute input model and the contract. Out of scope: authentication, who performs a transition, persistence in PostgreSQL, and any AI behavior. Data stays in memory for this feature."

## Clarifications

### Session 2026-11-15

- Q: Can a dispute "under_review" be withdrawn, or only an "open" one? → A: Yes. "under_review → withdrawn" is allowed in addition to "open → withdrawn".
- Q: Can an "open" dispute be rejected directly, without going through "under_review"? → A: No. Every rejection goes through "under_review" first, so each rejection has a recorded review.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Move a dispute through its lifecycle (Priority: P1)

Support staff handling a dispute change its state as the case progresses: an open dispute is
taken into review, and a dispute under review is closed as resolved or rejected. A customer who
no longer wants to pursue a dispute, whether it is still open or already under review,
withdraws it. Each change is requested by naming the
target state and, optionally, adding a short note explaining why. The system applies the change
and returns the updated dispute.

**Why this priority**: Without state changes a dispute can never be worked or closed, so the
product has no lifecycle. This is the core value of the feature.

**Independent Test**: Create a dispute, request the move to "under_review", then to "resolved",
and confirm after each step that the returned dispute shows the new state.

**Acceptance Scenarios**:

1. **Given** a dispute in state "open", **When** a transition to "under_review" is requested,
   **Then** the dispute is now "under_review" and the updated dispute is returned.
2. **Given** a dispute in state "under_review", **When** a transition to "resolved" is
   requested, **Then** the dispute is now "resolved".
3. **Given** a dispute in state "under_review", **When** a transition to "rejected" is
   requested, **Then** the dispute is now "rejected".
4. **Given** a dispute in state "open", **When** a transition to "withdrawn" is requested,
   **Then** the dispute is now "withdrawn".
5. **Given** a dispute in state "under_review", **When** a transition to "withdrawn" is
   requested, **Then** the dispute is now "withdrawn".
6. **Given** a transition request that includes a note, **When** it succeeds, **Then** the note
   is kept with that state change.
7. **Given** a transition request without a note, **When** it succeeds, **Then** the change is
   applied and recorded with no note.

---

### User Story 2 - Refuse invalid transitions and never reopen closed disputes (Priority: P1)

The system accepts only the allowed transitions. Any other request is refused with a clear
error and leaves the dispute exactly as it was. A closed dispute (resolved, rejected or
withdrawn) can never change again.

**Why this priority**: Disputes are a financial process; an invalid or reversible state
corrupts the audit trail. This is as essential as the transitions themselves (constitution,
principle II).

**Independent Test**: For every pair of states, request the transition and confirm that exactly
the allowed pairs succeed and all others are refused with the dispute unchanged.

**Acceptance Scenarios**:

1. **Given** a dispute in state "open", **When** a transition directly to "resolved" or
   directly to "rejected" is requested, **Then** the request is refused as a conflict and the
   dispute stays "open". Resolving or rejecting always requires passing through "under_review".
2. **Given** a dispute in state "resolved", "rejected" or "withdrawn", **When** any transition
   is requested, including back to "open", **Then** the request is refused and the dispute is
   unchanged.
3. **Given** a dispute in some state, **When** a transition to that same state is requested,
   **Then** the request is refused as a conflict.
4. **Given** a refused transition, **When** the dispute is fetched afterwards, **Then** its
   state, last-updated time and history are exactly what they were before the request.
5. **Given** a target state that is not one of the five known states, **When** a transition is
   requested, **Then** the request is rejected as invalid input, not as a conflict.
6. **Given** a request that is missing the target state, or contains unknown fields, **When**
   it is sent, **Then** it is rejected as invalid input and the error names the field at fault.
7. **Given** an id that matches no dispute, **When** a transition is requested, **Then** the
   system answers that the dispute was not found.
8. **Given** an id that is not in a valid id format, **When** a transition is requested,
   **Then** the system answers with a clear error rather than failing unexpectedly.

---

### User Story 3 - Resolve concurrent transitions safely (Priority: P1)

When two people act on the same dispute at the same moment with incompatible actions (for
example, one resolves it while another rejects it), exactly one action takes effect and the
other is told it conflicts. A final state is never silently overwritten and no dispute ends up
in a state that no sequence of allowed transitions could produce.

**Why this priority**: A race on a financial decision must not lose or overwrite a final
outcome. The plan names this as the proof of completion for the feature.

**Independent Test**: Send two incompatible transition requests for the same dispute at the same
time, repeat many times, and confirm every round has exactly one success and one conflict, and
that the final state matches the successful request.

**Acceptance Scenarios**:

1. **Given** a dispute "under_review", **When** a request to resolve it and a request to reject
   it arrive at the same time, **Then** exactly one succeeds, the other is refused as a
   conflict, and the dispute ends in the state of the successful request.
2. **Given** a dispute "open", **When** a request to take it under review and a request to
   withdraw it arrive at the same time, **Then** the outcome is one that could have happened
   with the two requests handled one after the other: either only one succeeds and the other
   is refused as a conflict, or both succeed in order (under review, then withdrawn). The
   history never shows a change that does not follow from the previous one.
3. **Given** a dispute "under_review", **When** a request to withdraw it and a request to
   resolve it (or to reject it) arrive at the same time, **Then** exactly one succeeds, the
   other is refused as a conflict, and the dispute ends in the state of the successful request.
4. **Given** many concurrent requests for the same transition on the same dispute, **When** they
   are processed, **Then** at most one succeeds, and the history contains that change only once.
5. **Given** concurrent requests on different disputes, **When** they are processed, **Then**
   they do not interfere with each other.

---

### User Story 4 - See when a dispute changed and why (Priority: P2)

A person reviewing a dispute can see when it was last updated and read the full history of its
state changes: from which state, to which state, the note given, and when. This lets them
reconstruct who did what to the case, in order.

**Why this priority**: The history makes the lifecycle auditable, but it only has content once
transitions exist.

**Independent Test**: Move a dispute through two transitions with notes, then read the dispute
and its history and confirm both entries appear in order with the right data.

**Acceptance Scenarios**:

1. **Given** a newly created dispute, **When** it is fetched, **Then** its last-updated time
   equals its creation time and its history is empty.
2. **Given** a dispute that went through several transitions, **When** its history is read,
   **Then** every successful transition appears once, in chronological order, with from state,
   to state, note (if any) and time.
3. **Given** a successful transition, **When** the dispute is fetched, **Then** its
   last-updated time is the time of that transition, not earlier than before.
4. **Given** a refused transition, **When** the dispute is fetched, **Then** its last-updated
   time and history are unchanged.

---

### User Story 5 - Use the renamed reason (Priority: P3)

The reason "devolution" is replaced by "refund_not_received", which states more clearly what the
customer is claiming (a refund they were promised never arrived). New disputes use the new
name; the old name is no longer accepted.

**Why this priority**: It is a naming correction that does not depend on state changes. It is
bundled here because the plan schedules it with this feature.

**Independent Test**: Open a dispute with reason "refund_not_received" and confirm it is
accepted; open one with "devolution" and confirm it is rejected.

**Acceptance Scenarios**:

1. **Given** valid dispute data with reason "refund_not_received", **When** the dispute is
   opened, **Then** it is created with that reason.
2. **Given** valid dispute data with reason "devolution", **When** the dispute is opened,
   **Then** the request is rejected and the error identifies the reason.

---

### Edge Cases

- Transition to the same state the dispute is already in (refused as a conflict).
- Transition to a state that skips a step, such as "open" to "resolved" or "open" to
  "rejected" (refused).
- Any transition out of "resolved", "rejected" or "withdrawn" (refused, including "open").
- Target state in a different case or spelling than the known list, such as "Resolved" (invalid input).
- Note that is empty, whitespace only, or longer than the maximum length (see Assumptions).
- Request body that is empty, is not valid JSON, or has extra fields such as a client-supplied
  last-updated time or previous state (invalid input).
- Two identical requests at the same moment (one succeeds, the other conflicts).
- Many rounds of racing requests in a row, to catch intermittent failures.
- A transition request for a dispute whose id is valid but unknown (not found, takes
  precedence over any state check).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support exactly these dispute states: open, under_review,
  resolved, rejected, withdrawn. Every new dispute MUST still start in "open".
- **FR-002**: The system MUST allow exactly these transitions: open to under_review,
  under_review to resolved, under_review to rejected, open to withdrawn, and under_review to
  withdrawn. Every other transition MUST be refused.
- **FR-003**: The states "resolved", "rejected" and "withdrawn" MUST be terminal: no transition
  out of them is allowed, and a closed dispute MUST never return to "open".
- **FR-004**: The set of allowed transitions MUST be defined in a single place in the domain,
  and every transition request MUST be checked against it.
- **FR-005**: A client MUST be able to request a transition by sending the target state and an
  optional note to the transitions action of a dispute (`POST /disputes/{id}/transitions`,
  body `to_state` and `note`).
- **FR-006**: A successful transition MUST update the dispute's state and return the full
  updated dispute.
- **FR-007**: A refused transition MUST leave the dispute unchanged: state, last-updated time
  and history.
- **FR-008**: The system MUST answer "not found" when the id matches no dispute, "invalid
  input" when the body is malformed, the target state is not one of the five known states, or
  the id is not a valid id, and "conflict" when the transition is not allowed from the current
  state (including a transition to the current state). These map to 404, 422 and 409.
- **FR-009**: Every error, including conflicts, MUST use the project's single consistent error
  format, and MUST name the field at fault when the cause is a specific input field. A conflict
  is caused by the relation between the requested state and the dispute's current state, not by
  a malformed field, so it names no field; its message states the current state or, when the
  state changed while the request was being handled, says so.
- **FR-010**: The system MUST reject unknown fields in a transition request, so the client
  cannot set the previous state, the last-updated time or any other system-assigned value.
- **FR-011**: Each dispute MUST have a last-updated time. It MUST equal the creation time when
  the dispute is created and MUST be set to the time of every successful transition.
- **FR-012**: The system MUST keep, for each dispute, a history of its successful state changes.
  Each entry MUST contain the from state, the to state, the note (if any) and the time of the
  change.
- **FR-013**: A client MUST be able to read a dispute's history through the API, in
  chronological order. A refused request MUST NOT add an entry.
- **FR-014**: When two or more transition requests for the same dispute are processed at the
  same time, every state change that is applied MUST be a valid transition from the state the
  dispute was actually in at that moment. Of requests that can never both succeed in any order
  (for example resolve and reject), exactly one MUST succeed and the others MUST be refused as
  conflicts. A request whose starting state changed while it was being handled MAY be refused
  as a conflict. A final state MUST never be silently overwritten.
- **FR-015**: Concurrent requests for different disputes MUST NOT affect each other.
- **FR-016**: The reason "devolution" MUST be replaced by "refund_not_received" in dispute
  creation and in the published API contract. The old value MUST be rejected as invalid input.
- **FR-017**: The README, the API contract of this feature and the architecture notes MUST be
  updated to describe state transitions, the history and the renamed reason, and MUST NOT claim
  anything that is not implemented and tested.

### Key Entities

- **Dispute**: A customer's complaint about a card transaction (as in feature 001). New
  attributes: state (now one of five values), last-updated time, and a history of state changes.
- **Dispute state**: One of open, under_review, resolved, rejected, withdrawn. "resolved",
  "rejected" and "withdrawn" are terminal.
- **Transition rule**: A permitted move from one state to another. The complete list lives in
  one place and is the only source of truth for what is allowed.
- **Transition request**: What a client sends to change a state: the target state and an
  optional note. It carries no system-assigned values.
- **State change (history entry)**: A record of one successful transition: from state, to
  state, optional note, time of the change.
- **Reason**: The fixed list of dispute reasons, with "devolution" replaced by
  "refund_not_received".

Names used in this spec and the names in the API: last-updated time is `updated_at`; the history
is `history`; each history entry has `from_state`, `to_state`, `note` and `changed_at` (the "time
of the change"); the target state of a request is `to_state`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A dispute can go from "open" to a closed state through the allowed path in two
  requests or fewer, and the result is visible immediately in the response.
- **SC-002**: Of all 25 combinations of current state and requested state, exactly the 5
  allowed ones succeed and the other 20 are refused, each one covered by an automated test.
- **SC-003**: 100% of refused transitions leave the dispute's state, last-updated time and
  history identical to before the request.
- **SC-004**: In a repeated race of two incompatible requests on the same dispute (at least 50
  rounds, each with a fresh dispute), every round produces exactly one success and one
  conflict, and the dispute's final state matches the successful request.
- **SC-005**: No closed dispute changes state in any test, including when requests arrive
  concurrently.
- **SC-006**: Every successful transition appears in the dispute's history exactly once, with
  correct from state, to state, note and time, and the last-updated time matches the latest
  entry.
- **SC-007**: Every error response, including conflicts, follows the same format as all other
  errors and names the field at fault when the cause is a specific field.
- **SC-008**: The old reason "devolution" is rejected and "refund_not_received" is accepted in
  100% of tested cases.
- **SC-009**: Every behavior above is covered by an automated test that was written, and seen
  to fail, before the implementation.

## Assumptions

- Authentication, authorization and who performs a transition are out of scope. The history
  records no actor. Anyone who can call the API can request any allowed transition.
- Data stays in memory in this feature and is lost on restart. Durable storage arrives with the
  later PostgreSQL feature, which will have to preserve the same conflict guarantees.
- The service may run with a single process. Guarantees about concurrent requests apply to
  requests handled by the same running instance; cross-instance coordination arrives with
  PostgreSQL.
- The note is optional, has a maximum of 1000 characters (the same as a dispute description),
  and is stored as sent. A request whose note is longer is rejected as invalid input. An
  empty or whitespace-only note is treated as no note.
- Creating a dispute is not a history entry: the history lists only transitions, so a new
  dispute has an empty history. Last-updated time starts equal to creation time.
- A dispute's history is readable through the API as part of the dispute itself (the response
  of fetching or changing a dispute includes it); there is no separate history resource in this
  feature (decided in the plan, research.md section 5).
- No disputes exist as persisted data before this feature, because storage is in memory;
  nothing needs migrating.
- Opening a dispute is unchanged from feature 001 except for the renamed reason.
- A direct "open" to "rejected" shortcut for obviously invalid disputes is not part of this
  feature; it could be added later as its own change.
- Out of scope: authentication, who performs a transition, persistence in PostgreSQL, listing
  or searching disputes, deleting disputes, notifications, and any AI behavior.
