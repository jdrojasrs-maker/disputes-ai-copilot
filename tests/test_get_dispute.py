from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

VALID_PAYLOAD = {
    "transaction_id": "txn_0001",
    "customer_id": "cust_0001",
    "amount": "125.50",
    "currency": "USD",
    "reason": "duplicate_charge",
    "description": "Charged twice for the same purchase",
}


def test_fetch_returns_the_dispute_that_was_created(client: TestClient):
    created = client.post("/disputes", json=VALID_PAYLOAD).json()

    response = client.get(f"/disputes/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created
    assert response.json()["state"] == "open"


def test_unknown_id_returns_not_found(client: TestClient):
    response = client.get(f"/disputes/{uuid4()}")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"] == []


def test_malformed_id_returns_validation_error(client: TestClient):
    response = client.get("/disputes/not-a-uuid")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert [detail["field"] for detail in error["details"]] == ["dispute_id"]


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_disputes_cannot_be_changed_or_deleted(client: TestClient, method: str):
    created = client.post("/disputes", json=VALID_PAYLOAD).json()

    response = client.request(method, f"/disputes/{created['id']}")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert client.get(f"/disputes/{created['id']}").json() == created
