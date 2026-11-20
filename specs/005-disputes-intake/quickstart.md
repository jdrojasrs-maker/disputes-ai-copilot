# Quickstart: validating dispute intake

Prerequisites: `uv sync`. Nothing here needs a key or the network except the optional manual
call at the end.

## 1. Automated proof (no key, no network)

```text
uv run pytest tests/test_intake.py tests/test_intake_checks.py
uv run pytest
uv run ruff check .
```

Expected: the new tests pass, the whole suite passes (the existing 434 tests are untouched),
ruff is clean. Every intake test uses `FakeLLMClient`; the network guard in `tests/conftest.py`
fails any test that reaches a remote host.

What each outcome in the contract table is proven by is listed in `plan.md`, "Test plan".

## 2. Look at the contract in the generated docs

```text
uv run uvicorn disputes.main:app --reload
```

Open `http://127.0.0.1:8000/docs` and confirm `POST /disputes/intake` appears with the 201 and
the error responses from [contracts/intake-contract.md](contracts/intake-contract.md). Without
model settings, calling it returns `llm_not_configured` (500): that is the expected behavior,
not a bug.

## 3. Optional: one real call (manual evidence, not part of the tests)

Needs real settings in your local `.env` (never committed): `LLM_PROVIDER` (`anthropic` or
`azure_openai`) plus that adapter's variables from `.env.example`. Send one synthetic message
whose transaction id and customer id are in the sample data, and record the result in
`docs/evidence/` the way features 003 and 004 did.

This single call proves the prompt works with one model once. It does **not** measure accuracy,
latency or cost; those belong to the evals feature (E5), and the README must not claim them.
