from datetime import datetime
from itertools import product

import pytest
from fastapi.testclient import TestClient

from disputes.models import DisputeState

S = DisputeState

VALID_PAYLOAD = {
    "transaction_id": "txn_0001",
    "customer_id": "cust_0001",
    "amount": "125.50",
    "currency": "USD",
    "reason": "duplicate_charge",
}

# Valid moves that lead from a new (open) dispute to each state.
PATH_TO = {
    S.OPEN: [],
    S.UNDER_REVIEW: [S.UNDER_REVIEW],
    S.RESOLVED: [S.UNDER_REVIEW, S.RESOLVED],
    S.REJECTED: [S.UNDER_REVIEW, S.REJECTED],
    S.WITHDRAWN: [S.WITHDRAWN],
}

ALLOWED_PAIRS = [
    (S.OPEN, S.UNDER_REVIEW),
    (S.OPEN, S.WITHDRAWN),
    (S.UNDER_REVIEW, S.RESOLVED),
    (S.UNDER_REVIEW, S.REJECTED),
    (S.UNDER_REVIEW, S.WITHDRAWN),
]


def create_dispute(client: TestClient) -> str:
    response = client.post("/disputes", json=VALID_PAYLOAD)
    assert response.status_code == 201
    return response.json()["id"]


def post_transition(client: TestClient, dispute_id: str, to_state: DisputeState, **extra):
    return client.post(
        f"/disputes/{dispute_id}/transitions", json={"to_state": to_state.value, **extra}
    )


def dispute_in_state(client: TestClient, state: DisputeState) -> str:
    """Create a dispute and drive it to `state` through valid transitions."""
    dispute_id = create_dispute(client)
    for step in PATH_TO[state]:
        assert post_transition(client, dispute_id, step).status_code == 200
    return dispute_id


@pytest.mark.parametrize(("from_state", "to_state"), ALLOWED_PAIRS)
def test_allowed_transition_returns_the_dispute_in_its_new_state(
    client: TestClient, from_state: DisputeState, to_state: DisputeState
):
    dispute_id = dispute_in_state(client, from_state)

    response = post_transition(client, dispute_id, to_state)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == dispute_id
    assert body["state"] == to_state.value


def test_a_note_is_stored_in_the_history_entry(client: TestClient):
    dispute_id = create_dispute(client)

    response = post_transition(client, dispute_id, S.UNDER_REVIEW, note="checking with the bank")

    assert response.json()["history"][0]["note"] == "checking with the bank"


def test_no_note_is_stored_as_null(client: TestClient):
    dispute_id = create_dispute(client)

    response = post_transition(client, dispute_id, S.UNDER_REVIEW)

    assert response.json()["history"][0]["note"] is None


def test_the_response_equals_a_following_get(client: TestClient):
    dispute_id = create_dispute(client)

    response = post_transition(client, dispute_id, S.UNDER_REVIEW, note="x")

    assert client.get(f"/disputes/{dispute_id}").json() == response.json()


def test_two_steps_in_a_row_leave_the_dispute_resolved(client: TestClient):
    dispute_id = create_dispute(client)

    first = post_transition(client, dispute_id, S.UNDER_REVIEW)
    second = post_transition(client, dispute_id, S.RESOLVED)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["state"] == "resolved"
    assert client.get(f"/disputes/{dispute_id}").json()["state"] == "resolved"


# --- Refused transitions and validation (US2) ---------------------------------

ALL_PAIRS = list(product(DisputeState, DisputeState))
REFUSED_PAIRS = [pair for pair in ALL_PAIRS if pair not in ALLOWED_PAIRS]
CLOSED_STATES = [S.RESOLVED, S.REJECTED, S.WITHDRAWN]


def get_dispute(client: TestClient, dispute_id: str) -> dict:
    response = client.get(f"/disputes/{dispute_id}")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(("from_state", "to_state"), ALL_PAIRS)
def test_exactly_the_five_allowed_pairs_succeed(
    client: TestClient, from_state: DisputeState, to_state: DisputeState
):
    dispute_id = dispute_in_state(client, from_state)

    response = post_transition(client, dispute_id, to_state)

    if (from_state, to_state) in ALLOWED_PAIRS:
        assert response.status_code == 200
        return
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "invalid_transition"
    assert error["details"] == []
    assert from_state.value in error["message"]
    assert to_state.value in error["message"]


@pytest.mark.parametrize(("from_state", "to_state"), REFUSED_PAIRS)
def test_a_refused_transition_leaves_the_dispute_unchanged(
    client: TestClient, from_state: DisputeState, to_state: DisputeState
):
    dispute_id = dispute_in_state(client, from_state)
    before = get_dispute(client, dispute_id)

    post_transition(client, dispute_id, to_state, note="should not be recorded")

    assert get_dispute(client, dispute_id) == before


@pytest.mark.parametrize("closed_state", CLOSED_STATES)
def test_a_closed_dispute_is_never_reopened(client: TestClient, closed_state: DisputeState):
    dispute_id = dispute_in_state(client, closed_state)

    response = post_transition(client, dispute_id, S.OPEN)

    assert response.status_code == 409
    assert get_dispute(client, dispute_id)["state"] == closed_state.value


@pytest.mark.parametrize("to_state", ["closed", "Resolved"])
def test_an_unknown_state_is_a_validation_error(client: TestClient, to_state: str):
    dispute_id = create_dispute(client)

    response = client.post(f"/disputes/{dispute_id}/transitions", json={"to_state": to_state})

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert "to_state" in fields


def test_a_missing_to_state_is_a_validation_error(client: TestClient):
    dispute_id = create_dispute(client)

    response = client.post(f"/disputes/{dispute_id}/transitions", json={})

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert "to_state" in fields


def test_an_unknown_field_is_a_validation_error(client: TestClient):
    dispute_id = create_dispute(client)

    response = client.post(
        f"/disputes/{dispute_id}/transitions",
        json={"to_state": "under_review", "from_state": "open"},
    )

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert "from_state" in fields


def test_a_note_of_1001_characters_is_a_validation_error(client: TestClient):
    dispute_id = create_dispute(client)

    response = post_transition(client, dispute_id, S.UNDER_REVIEW, note="x" * 1001)

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert "note" in fields


def test_malformed_json_is_a_validation_error_on_the_body(client: TestClient):
    dispute_id = create_dispute(client)

    response = client.post(
        f"/disputes/{dispute_id}/transitions",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert fields == ["body"]


def test_a_request_without_a_body_is_a_validation_error_on_the_body(client: TestClient):
    dispute_id = create_dispute(client)

    response = client.post(f"/disputes/{dispute_id}/transitions")

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert fields == ["body"]


def test_an_unknown_dispute_is_not_found(client: TestClient):
    response = client.post(
        "/disputes/6f1c2b1e-0000-4000-8000-000000000000/transitions",
        json={"to_state": "under_review"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_malformed_id_is_a_validation_error_on_dispute_id(client: TestClient):
    response = client.post("/disputes/not-a-uuid/transitions", json={"to_state": "under_review"})

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert fields == ["dispute_id"]


def test_get_on_the_transitions_route_is_method_not_allowed(client: TestClient):
    dispute_id = create_dispute(client)

    response = client.get(f"/disputes/{dispute_id}/transitions")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_a_refused_request_adds_no_history_entry(client: TestClient):
    dispute_id = dispute_in_state(client, S.RESOLVED)
    entries_before = len(get_dispute(client, dispute_id)["history"])

    post_transition(client, dispute_id, S.REJECTED)

    assert len(get_dispute(client, dispute_id)["history"]) == entries_before


def test_a_lost_race_is_a_409_that_says_the_state_changed(client: TestClient, repository):
    dispute_id = create_dispute(client)
    real_transition = repository.transition

    def lose_the_race(dispute_id, from_state, to_state, note, at):
        # A competing request wins first, so the caller's `from_state` is stale.
        real_transition(dispute_id, S.OPEN, S.UNDER_REVIEW, None, at)
        return real_transition(dispute_id, from_state, to_state, note, at)

    repository.transition = lose_the_race

    response = post_transition(client, dispute_id, S.WITHDRAWN)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "invalid_transition"
    assert "changed" in error["message"]
    assert "under_review" in error["message"]
    assert "Cannot change state" not in error["message"]
    after = get_dispute(client, dispute_id)
    assert after["state"] == "under_review"
    assert len(after["history"]) == 1


# --- updated_at and history (US4) ---------------------------------------------


def test_history_lists_each_change_in_order_with_its_note(client: TestClient):
    dispute_id = create_dispute(client)
    post_transition(client, dispute_id, S.UNDER_REVIEW, note="checking with the bank")
    post_transition(client, dispute_id, S.RESOLVED, note="refund confirmed")

    dispute = get_dispute(client, dispute_id)

    history = dispute["history"]
    assert [(e["from_state"], e["to_state"], e["note"]) for e in history] == [
        ("open", "under_review", "checking with the bank"),
        ("under_review", "resolved", "refund confirmed"),
    ]
    for entry in history:
        assert datetime.fromisoformat(entry["changed_at"]).tzinfo is not None


def test_updated_at_follows_the_last_history_entry_and_time_never_goes_back(
    client: TestClient,
):
    dispute_id = create_dispute(client)
    post_transition(client, dispute_id, S.UNDER_REVIEW, note="first")
    post_transition(client, dispute_id, S.RESOLVED, note="second")

    dispute = get_dispute(client, dispute_id)

    created_at = datetime.fromisoformat(dispute["created_at"])
    updated_at = datetime.fromisoformat(dispute["updated_at"])
    changed_at = [datetime.fromisoformat(entry["changed_at"]) for entry in dispute["history"]]
    # Not strictly greater: two nearby clock reads are often equal, so the order of the entries,
    # not their timestamps, proves the sequence (research.md section 6).
    assert dispute["history"][-1]["changed_at"] == dispute["updated_at"]
    assert created_at <= changed_at[0] <= changed_at[1] == updated_at


def test_a_refused_transition_leaves_updated_at_and_history_identical(client: TestClient):
    dispute_id = dispute_in_state(client, S.RESOLVED)
    before = get_dispute(client, dispute_id)

    response = post_transition(client, dispute_id, S.REJECTED, note="too late")

    assert response.status_code == 409
    after = get_dispute(client, dispute_id)
    assert after["updated_at"] == before["updated_at"]
    assert after["history"] == before["history"]
