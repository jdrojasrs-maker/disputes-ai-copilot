# Feature Specification: Create and Get Dispute

**Feature Branch**: `feat/001-create-and-get-dispute`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "A customer can open a dispute about a card transaction and later look it up. Opening a dispute requires the transaction id, customer id, amount (greater than zero), currency, a reason from a fixed list (duplicate charge, unrecognized charge, product not received, incorrect amount, devolution) and an optional description up to 1000 characters. A new dispute always starts as open. Invalid input is rejected with a clear error. A dispute can be fetched by id; an unknown id returns not found. State changes are out of scope for this feature."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open a dispute (Priority: P1)

A customer who sees a problem with a card transaction opens a dispute by providing the
transaction, who they are, the amount in question, the currency, the reason, and optionally a
short description. The system records the dispute, assigns it a unique id and reports it as open.

**Why this priority**: Without the ability to open a dispute, nothing else in the product has
data to work with. It is the core value of the feature.

**Independent Test**: Submit a valid dispute and confirm the response contains a new id, the
submitted data, and the state "open".

**Acceptance Scenarios**:

1. **Given** valid transaction id, customer id, amount, currency and reason, **When** the
   customer opens a dispute, **Then** the dispute is created with a unique id and state "open".
2. **Given** valid input including a description of 1000 characters or fewer, **When** the
   dispute is opened, **Then** the description is stored with the dispute.
3. **Given** valid input without a description, **When** the dispute is opened, **Then** the
   dispute is created with no description.
4. **Given** any valid input, **When** a dispute is opened, **Then** its state is always
   "open", regardless of any state value sent by the caller.

---

### User Story 2 - Reject invalid disputes (Priority: P1)

When the information provided is incomplete or wrong, the system refuses to create the dispute
and tells the customer exactly what is wrong, so they can fix it and try again.

**Why this priority**: Accepting bad data would create unusable disputes; clear errors are part
of the minimum viable behavior.

**Independent Test**: Submit disputes with one invalid field each and confirm that none is
created and each response identifies the offending field.

**Acceptance Scenarios**:

1. **Given** an amount of zero or less, **When** the customer opens a dispute, **Then** the
   request is rejected and the error identifies the amount.
2. **Given** a reason not in the fixed list, **When** the customer opens a dispute, **Then** the
   request is rejected and the error identifies the reason.
3. **Given** a missing transaction id, customer id, amount, currency or reason, **When** the
   customer opens a dispute, **Then** the request is rejected and the error identifies the
   missing field.
4. **Given** a description longer than 1000 characters, **When** the customer opens a dispute,
   **Then** the request is rejected and the error identifies the description.
5. **Given** any rejected request, **When** the system is inspected afterwards, **Then** no
   dispute was created by that request.

---

### User Story 3 - Look up a dispute (Priority: P2)

A customer (or support staff on their behalf) retrieves a previously opened dispute by its id to
see its data and current state.

**Why this priority**: Lookup completes the "open then follow up" journey, but it depends on
disputes existing first.

**Independent Test**: Open a dispute, then fetch it by the returned id and confirm the data
matches; fetch an unknown id and confirm "not found".

**Acceptance Scenarios**:

1. **Given** an existing dispute, **When** it is fetched by its id, **Then** the full dispute is
   returned, including state "open", with the same data that was submitted.
2. **Given** an id that matches no dispute, **When** it is fetched, **Then** the system answers
   that the dispute was not found.
3. **Given** an id that is not in a valid id format, **When** it is fetched, **Then** the system
   answers with a clear error rather than failing unexpectedly.

---

### Edge Cases

- Amount with more than two decimal places, or more than 12 digits in total (rejected).
- Currency that is empty, lowercase, or not exactly three uppercase letters (rejected).
- Description of exactly 1000 characters (accepted) and 1001 characters (rejected).
- Whitespace-only or empty transaction id or customer id.
- Request containing unknown extra fields, including an attempt to set the state.
- The same transaction disputed twice (see Assumptions).
- Reason sent in a different case or spelling than the fixed list.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow opening a dispute with a transaction id, customer id,
  amount, currency, reason and an optional description.
- **FR-002**: The system MUST reject a dispute whose amount is zero or negative, has more than
  two decimal places, or has more than 12 digits in total.
- **FR-003**: The system MUST accept only these reasons: duplicate charge, unrecognized charge,
  product not received, incorrect amount, devolution; any other value MUST be rejected.
- **FR-004**: The system MUST reject a dispute that omits the transaction id, customer id,
  amount, currency or reason, or where the transaction id or customer id is blank.
- **FR-005**: The system MUST accept a description of up to 1000 characters and reject longer
  ones; the description MUST be optional.
- **FR-006**: The system MUST assign each new dispute a unique id.
- **FR-007**: The system MUST set the state of every new dispute to "open" and MUST reject any
  caller attempt to choose the state.
- **FR-008**: The system MUST store each created dispute, with its creation time, so that it can
  be retrieved later.
- **FR-009**: The system MUST allow retrieving a dispute by id, returning all its data and its
  current state.
- **FR-010**: The system MUST answer "not found" when the requested id matches no dispute.
- **FR-011**: The system MUST NOT create any dispute when the input is invalid.
- **FR-012**: Every error MUST use the project's single consistent error format and name the
  field at fault when the cause is a specific input field.
- **FR-013**: Changing a dispute's state (including closing it) is out of scope; this feature
  MUST NOT provide any way to do so.

### Key Entities

- **Dispute**: A customer's complaint about a card transaction. Attributes: unique id,
  transaction id, customer id, amount, currency, reason, optional description, state (always
  "open" in this feature), creation time.
- **Reason**: A fixed set of values: duplicate charge, unrecognized charge, product not
  received, incorrect amount, devolution.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A customer can open a dispute with valid data in a single request and receive its
  id immediately in the response.
- **SC-002**: 100% of disputes created are in state "open" at creation.
- **SC-003**: 100% of requests with invalid input (non-positive amount, reason outside the list,
  missing required field, description over 1000 characters) are rejected, and none of them
  creates a dispute.
- **SC-004**: Every rejection tells the customer which field is wrong, without needing to read
  documentation or contact support.
- **SC-005**: A dispute fetched by id returns exactly the data that was submitted when it was
  opened (amounts compare as decimal values, so 125.5 equals 125.50), and an unknown id always yields "not found".
- **SC-006**: Every behavior above is covered by an automated test that was written before the
  implementation.

## Assumptions

- Caller identity and authorization are out of scope; the customer id is supplied in the
  request and trusted for now.
- The transaction id refers to a transaction in another system (e.g. Bank); this feature does
  not verify that the transaction exists.
- Customer id and transaction id are opaque text values; all example data is synthetic.
- Currency is a three-letter code (ISO 4217 style); the exact accepted list is decided in
  planning. Amounts are decimal money values with at most two decimal places.
- Opening more than one dispute for the same transaction is allowed in this feature; duplicate
  prevention is a possible later rule.
- Disputes are kept in memory in this feature and are lost on restart; durable storage arrives
  with the later PostgreSQL feature (see plan.md).
- Listing, searching, updating and deleting disputes, and any state change, are out of scope.
