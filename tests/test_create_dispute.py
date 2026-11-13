from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from disputes.repository import InMemoryDisputeRepository

VALID_PAYLOAD = {
    "transaction_id": "txn_0001",
    "customer_id": "cust_0001",
    "amount": "125.50",
    "currency": "USD",
    "reason": "duplicate_charge",
}


def test_valid_request_creates_an_open_dispute(client: TestClient):
    response = client.post("/disputes", json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    for field, value in VALID_PAYLOAD.items():
        assert body[field] == value
    assert UUID(body["id"]).version == 4
    assert body["state"] == "open"
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None
    assert body["description"] is None


def test_created_dispute_is_stored(client: TestClient, repository):
    response = client.post("/disputes", json=VALID_PAYLOAD)

    stored_id = UUID(response.json()["id"])
    assert repository.get(stored_id) is not None


def test_location_header_points_to_the_new_dispute(client: TestClient):
    response = client.post("/disputes", json=VALID_PAYLOAD)

    assert response.headers["Location"] == f"/disputes/{response.json()['id']}"


def test_description_is_optional_and_returned_when_given(client: TestClient):
    without = client.post("/disputes", json=VALID_PAYLOAD)
    with_description = client.post(
        "/disputes", json={**VALID_PAYLOAD, "description": "x" * 1000}
    )

    assert without.status_code == 201
    assert without.json()["description"] is None
    assert with_description.status_code == 201
    assert with_description.json()["description"] == "x" * 1000


def test_same_payload_twice_creates_two_disputes(client: TestClient):
    first = client.post("/disputes", json=VALID_PAYLOAD)
    second = client.post("/disputes", json=VALID_PAYLOAD)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.parametrize(
    "reason",
    [
        "duplicate_charge",
        "unrecognized_charge",
        "product_not_received",
        "incorrect_amount",
        "devolution",
    ],
)
def test_every_reason_is_accepted(client: TestClient, reason: str):
    response = client.post("/disputes", json={**VALID_PAYLOAD, "reason": reason})

    assert response.status_code == 201
    assert response.json()["reason"] == reason


# --- Rejected requests (US2) ------------------------------------------------


def without(payload: dict, field: str) -> dict:
    return {key: value for key, value in payload.items() if key != field}


INVALID_REQUESTS = [
    pytest.param({**VALID_PAYLOAD, "amount": "0"}, "amount", id="amount-zero"),
    pytest.param({**VALID_PAYLOAD, "amount": "-5"}, "amount", id="amount-negative"),
    pytest.param({**VALID_PAYLOAD, "reason": "refund"}, "reason", id="unknown-reason"),
    pytest.param(without(VALID_PAYLOAD, "transaction_id"), "transaction_id", id="no-transaction"),
    pytest.param(without(VALID_PAYLOAD, "customer_id"), "customer_id", id="no-customer"),
    pytest.param(without(VALID_PAYLOAD, "amount"), "amount", id="no-amount"),
    pytest.param(without(VALID_PAYLOAD, "currency"), "currency", id="no-currency"),
    pytest.param(without(VALID_PAYLOAD, "reason"), "reason", id="no-reason"),
    pytest.param({**VALID_PAYLOAD, "transaction_id": "   "}, "transaction_id", id="blank-id"),
    pytest.param({**VALID_PAYLOAD, "description": "x" * 1001}, "description", id="long-text"),
    pytest.param({**VALID_PAYLOAD, "state": "closed"}, "state", id="caller-sets-state"),
]


@pytest.mark.parametrize(("payload", "field"), INVALID_REQUESTS)
def test_invalid_request_is_rejected_and_nothing_is_stored(
    client: TestClient, repository: InMemoryDisputeRepository, payload: dict, field: str
):
    response = client.post("/disputes", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in [detail["field"] for detail in error["details"]]
    assert repository.disputes == {}


def test_malformed_json_is_rejected_and_nothing_is_stored(
    client: TestClient, repository: InMemoryDisputeRepository
):
    response = client.post(
        "/disputes", content=b"{not json", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert [detail["field"] for detail in error["details"]] == ["body"]
    assert repository.disputes == {}
