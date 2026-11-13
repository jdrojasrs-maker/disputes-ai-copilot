# disputes-ai-copilot Constitution

## Core Principles

### I. Tests First (NON-NEGOTIABLE)
Every behavior MUST have an automated test that fails before the implementation exists and
passes after it. The red-then-green order MUST be followed for each change: write the test,
watch it fail for the expected reason, then write the code. No behavior is merged without a
test that covers it.

Rationale: tests written first prove the test can fail and keep the code limited to what is
specified.

### II. Valid State Transitions Only
A dispute MUST move only through explicitly allowed state transitions, defined in one place
in the domain code. Any other transition MUST be rejected with an error and leave the dispute
unchanged. A closed dispute MUST never be reopened. Both the allowed and the rejected
transitions MUST be covered by tests.

Rationale: disputes are a financial process; an invalid or reversible state corrupts the
audit trail.

### III. Synthetic Data Only
The repository, logs, fixtures and tests MUST contain only synthetic data. Real customer data,
secrets, API keys and PII MUST NOT be committed or logged. Secrets MUST be read from the
environment, and example configuration files MUST contain placeholders only.

Rationale: the repository is public; anything committed is permanently exposed.

### IV. Validate at the Boundary
All external input MUST be validated by Pydantic v2 models at the API boundary before reaching
domain logic. All API errors MUST use a single consistent response format, covering validation
errors, domain errors (such as invalid transitions) and not-found cases. The format MUST be
covered by tests.

Rationale: validating once at the edge keeps the domain code simple and gives clients
predictable errors.

### V. Independent Service
This service MUST own its database and schema. It MUST NOT modify the Bank project or its
database, and MUST NOT depend on Bank internals. Any interaction with Bank MUST go through a
documented interface and use synthetic data.

Rationale: independent services can be built, tested and deployed on their own.

### VI. Honest Documentation
The README and all docs MUST claim only what exists and is tested. Metrics and figures MUST be
measured, never invented. Planned features MUST be labeled as planned.

Rationale: this is a portfolio project; claims that cannot be demonstrated damage credibility.

## Technical Constraints

- Language and framework: Python 3.12, FastAPI, Pydantic v2.
- Tooling: uv for dependencies and execution, ruff for lint, pytest for tests.
- Persistence: PostgreSQL with SQLAlchemy (async) and Alembic migrations. These arrive in a
  later feature; until then, no code MUST assume them beyond what that feature introduces.
- Local environment: Docker Compose for supporting services such as Postgres.
- Adding a new core dependency or replacing one of the above requires a constitution amendment
  or a documented justification in the feature plan.

## Development Workflow

- Work happens on feature branches with pull requests into `develop`; `main` receives merges
  only from `develop`.
- CI (tests and lint) MUST be green before a PR is merged.
- Each session covers one topic and one deliverable.
- The author MUST be able to explain every line of AI-generated code before committing it.
- Features follow Spec Kit: spec, plan, tasks, then implementation, with tests first.

## Governance

This constitution supersedes other project practices. Amendments MUST be made through a pull
request that updates this file, states the reason, and updates any affected docs.
Versioning follows semantic versioning: MAJOR for removing or redefining a principle in an
incompatible way, MINOR for adding a principle or materially expanding guidance, PATCH for
clarifications and wording fixes. Every PR review MUST check compliance with these principles,
and any deviation MUST be justified in the PR description. Runtime guidance for the AI assistant
lives in `CLAUDE.md`.

**Version**: 1.0.0 | **Ratified**: 2026-11-10 | **Last Amended**: 2026-11-10
