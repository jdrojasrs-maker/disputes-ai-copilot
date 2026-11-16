"""Concurrent transitions through the HTTP API.

These rounds check safety: whatever the timing, no round may end in an invalid result. A barrier
starts the requests together but cannot force the handlers to interleave, so these tests alone do
not prove the lock is needed; `test_transition_is_atomic_under_a_slow_read` in
`test_repository.py` does.
"""

import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from disputes.models import DisputeState

S = DisputeState

ROUNDS = 50
HANG_TIMEOUT = 20  # seconds; a round normally takes a few milliseconds

VALID_PAYLOAD = {
    "transaction_id": "txn_0001",
    "customer_id": "cust_0001",
    "amount": "125.50",
    "currency": "USD",
    "reason": "duplicate_charge",
}

PATH_TO = {
    S.OPEN: [],
    S.UNDER_REVIEW: [S.UNDER_REVIEW],
    S.RESOLVED: [S.UNDER_REVIEW, S.RESOLVED],
    S.REJECTED: [S.UNDER_REVIEW, S.REJECTED],
    S.WITHDRAWN: [S.WITHDRAWN],
}


def dispute_in_state(client: TestClient, state: DisputeState) -> str:
    response = client.post("/disputes", json=VALID_PAYLOAD)
    assert response.status_code == 201
    dispute_id = response.json()["id"]
    for step in PATH_TO[state]:
        step_response = client.post(
            f"/disputes/{dispute_id}/transitions", json={"to_state": step.value}
        )
        assert step_response.status_code == 200
    return dispute_id


def get_dispute(client: TestClient, dispute_id: str) -> dict:
    response = client.get(f"/disputes/{dispute_id}")
    assert response.status_code == 200
    return response.json()


def race(client: TestClient, requests: Sequence[tuple[str, DisputeState]]) -> list:
    """Send every (dispute_id, to_state) request at once and return the responses in order."""
    barrier = threading.Barrier(len(requests), timeout=HANG_TIMEOUT)

    def send(dispute_id: str, to_state: DisputeState):
        barrier.wait()
        return client.post(
            f"/disputes/{dispute_id}/transitions", json={"to_state": to_state.value}
        )

    # A round that hangs must fail with a message, not block the whole test run, so the pool is
    # not used as a context manager (its exit would wait for the stuck threads).
    pool = ThreadPoolExecutor(len(requests))
    try:
        futures = [pool.submit(send, dispute_id, to_state) for dispute_id, to_state in requests]
        return [future.result(timeout=HANG_TIMEOUT) for future in futures]
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def assert_consistent(dispute: dict) -> None:
    """The invariant from data-model.md: an unbroken history and time that never goes back."""
    history = dispute["history"]
    created_at = datetime.fromisoformat(dispute["created_at"])
    updated_at = datetime.fromisoformat(dispute["updated_at"])
    if not history:
        assert dispute["state"] == "open"
        assert updated_at == created_at
        return
    assert history[0]["from_state"] == "open"
    for previous, entry in zip(history, history[1:], strict=False):
        assert entry["from_state"] == previous["to_state"]
    assert history[-1]["to_state"] == dispute["state"]
    times = [created_at] + [datetime.fromisoformat(entry["changed_at"]) for entry in history]
    assert times == sorted(times)
    assert times[-1] == updated_at


def statuses(responses: list) -> list[int]:
    return sorted(response.status_code for response in responses)


@pytest.mark.parametrize(
    ("first", "second"),
    [(S.RESOLVED, S.REJECTED), (S.WITHDRAWN, S.RESOLVED), (S.WITHDRAWN, S.REJECTED)],
)
def test_incompatible_moves_from_under_review_have_exactly_one_winner(
    client: TestClient, first: DisputeState, second: DisputeState
):
    for _ in range(ROUNDS):
        dispute_id = dispute_in_state(client, S.UNDER_REVIEW)

        responses = race(client, [(dispute_id, first), (dispute_id, second)])

        assert statuses(responses) == [200, 409]
        winner = next(response for response in responses if response.status_code == 200)
        loser = next(response for response in responses if response.status_code == 409)
        assert loser.json()["error"]["code"] == "invalid_transition"
        dispute = get_dispute(client, dispute_id)
        assert dispute["state"] == winner.json()["state"]
        assert len(dispute["history"]) == 2
        assert_consistent(dispute)


def test_two_identical_moves_have_exactly_one_winner(client: TestClient):
    for _ in range(ROUNDS):
        dispute_id = dispute_in_state(client, S.OPEN)

        responses = race(client, [(dispute_id, S.UNDER_REVIEW)] * 2)

        assert statuses(responses) == [200, 409]
        dispute = get_dispute(client, dispute_id)
        assert dispute["state"] == "under_review"
        assert len(dispute["history"]) == 1
        assert_consistent(dispute)


def test_under_review_against_withdrawn_from_open_ends_in_one_of_three_ways(
    client: TestClient,
):
    for _ in range(ROUNDS):
        dispute_id = dispute_in_state(client, S.OPEN)

        under_review, withdrawn = race(
            client, [(dispute_id, S.UNDER_REVIEW), (dispute_id, S.WITHDRAWN)]
        )

        dispute = get_dispute(client, dispute_id)
        outcome = (under_review.status_code, withdrawn.status_code, dispute["state"])
        assert outcome in {
            (200, 409, "under_review"),  # under_review won; withdrawn lost
            (409, 200, "withdrawn"),  # withdrawn won; under_review lost
            (200, 200, "withdrawn"),  # under_review applied first, then withdrawn
        }
        assert_consistent(dispute)


def test_ten_identical_moves_at_once_have_exactly_one_winner(client: TestClient):
    dispute_id = dispute_in_state(client, S.OPEN)

    responses = race(client, [(dispute_id, S.UNDER_REVIEW)] * 10)

    assert statuses(responses) == [200] + [409] * 9
    dispute = get_dispute(client, dispute_id)
    assert len(dispute["history"]) == 1
    assert_consistent(dispute)


def test_moves_on_different_disputes_at_once_both_succeed(client: TestClient):
    for _ in range(ROUNDS):
        first = dispute_in_state(client, S.OPEN)
        second = dispute_in_state(client, S.OPEN)

        responses = race(client, [(first, S.UNDER_REVIEW), (second, S.UNDER_REVIEW)])

        assert statuses(responses) == [200, 200]
        assert_consistent(get_dispute(client, first))
        assert_consistent(get_dispute(client, second))


@pytest.mark.parametrize("closed_state", [S.RESOLVED, S.REJECTED, S.WITHDRAWN])
def test_a_closed_dispute_is_never_changed_by_simultaneous_requests(
    client: TestClient, closed_state: DisputeState
):
    dispute_id = dispute_in_state(client, closed_state)
    others = [state for state in (S.RESOLVED, S.REJECTED, S.WITHDRAWN) if state != closed_state]
    attempts = [S.OPEN, *others]
    before = get_dispute(client, dispute_id)

    for _ in range(ROUNDS):
        responses = race(client, [(dispute_id, state) for state in attempts])

        assert statuses(responses) == [409, 409, 409]
        assert get_dispute(client, dispute_id) == before
