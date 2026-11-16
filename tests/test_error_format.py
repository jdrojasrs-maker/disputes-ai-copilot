from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from disputes.errors import (
    DisputeNotFoundError,
    InvalidTransitionError,
    register_error_handlers,
)
from disputes.models import DisputeState


class Item(BaseModel):
    amount: int = Field(gt=0)


def build_client() -> TestClient:
    """Small app with routes that fail in each way the real API can fail."""
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/items")
    def create_item(item: Item) -> Item:
        return item

    @app.get("/items/{item_id}")
    def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/missing")
    def missing() -> None:
        raise DisputeNotFoundError()

    @app.post("/not-allowed")
    def not_allowed() -> None:
        raise InvalidTransitionError(
            from_state=DisputeState.RESOLVED, to_state=DisputeState.REJECTED
        )

    @app.post("/lost-race")
    def lost_race() -> None:
        raise InvalidTransitionError(
            from_state=DisputeState.UNDER_REVIEW,
            to_state=DisputeState.WITHDRAWN,
            state_changed=True,
        )

    return TestClient(app)


client = build_client()


def test_validation_error_uses_the_standard_envelope():
    response = client.post("/items", json={"amount": 0})

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["message"], str)
    assert len(body["error"]["details"]) == 1
    detail = body["error"]["details"][0]
    assert isinstance(detail["message"], str)
    assert set(detail) == {"field", "message"}


def test_body_field_name_drops_the_location_prefix():
    response = client.post("/items", json={"amount": 0})

    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert fields == ["amount"]


def test_missing_field_is_named():
    response = client.post("/items", json={})

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert fields == ["amount"]


def test_path_field_name_drops_the_location_prefix():
    response = client.get("/items/not-a-number")

    assert response.status_code == 422
    fields = [detail["field"] for detail in response.json()["error"]["details"]]
    assert fields == ["item_id"]


def test_malformed_json_reports_body_as_the_field():
    response = client.post(
        "/items",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    fields = [detail["field"] for detail in body["error"]["details"]]
    assert fields == ["body"]


def test_not_found_uses_the_standard_envelope():
    response = client.get("/missing")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["details"] == []


def test_unknown_route_uses_the_standard_envelope():
    response = client.get("/no-such-route")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "not_found"
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["details"] == []


def test_method_not_allowed_uses_the_standard_envelope():
    response = client.put("/items/1")

    assert response.status_code == 405
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "method_not_allowed"
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["details"] == []


def test_method_not_allowed_keeps_the_allow_header():
    response = client.put("/items/1")

    assert "GET" in response.headers["Allow"]


def test_invalid_transition_uses_the_standard_envelope():
    response = client.post("/not-allowed")

    assert response.status_code == 409
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "invalid_transition"
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["details"] == []


def test_invalid_transition_message_names_both_states():
    message = client.post("/not-allowed").json()["error"]["message"]

    assert "resolved" in message
    assert "rejected" in message


def test_lost_race_uses_the_same_code_but_says_the_state_changed():
    response = client.post("/lost-race")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "invalid_transition"
    assert error["details"] == []
    assert "changed" in error["message"]
    assert "under_review" in error["message"]
    # The move may be allowed from the new state, so it must not claim it is refused.
    assert "Cannot change state" not in error["message"]
