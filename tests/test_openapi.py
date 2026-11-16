from disputes.main import app

schema = app.openapi()
POST = schema["paths"]["/disputes"]["post"]["responses"]
GET = schema["paths"]["/disputes/{dispute_id}"]["get"]["responses"]


def error_schema_ref(response: dict) -> str:
    return response["content"]["application/json"]["schema"]["$ref"]


def test_validation_errors_are_documented_with_the_standard_envelope():
    assert error_schema_ref(POST["422"]).endswith("/ErrorResponse")
    assert error_schema_ref(GET["422"]).endswith("/ErrorResponse")


def test_get_documents_not_found_with_the_standard_envelope():
    assert error_schema_ref(GET["404"]).endswith("/ErrorResponse")


def test_create_documents_the_location_header():
    assert "Location" in POST["201"]["headers"]


def test_dispute_response_always_includes_state():
    required = schema["components"]["schemas"]["Dispute"]["required"]

    assert {"id", "state", "created_at"} <= set(required)


TRANSITIONS = schema["paths"]["/disputes/{dispute_id}/transitions"]["post"]["responses"]


def test_transitions_documents_the_updated_dispute_on_success():
    ref = TRANSITIONS["200"]["content"]["application/json"]["schema"]["$ref"]

    assert ref.endswith("/Dispute")


def test_transitions_documents_not_found_conflict_and_validation_errors():
    for status in ("404", "409", "422"):
        assert error_schema_ref(TRANSITIONS[status]).endswith("/ErrorResponse")


def test_transition_request_requires_only_to_state():
    request = schema["components"]["schemas"]["TransitionRequest"]

    assert request["required"] == ["to_state"]


def test_dispute_schema_requires_updated_at_and_history():
    required = schema["components"]["schemas"]["Dispute"]["required"]

    assert {"updated_at", "history"} <= set(required)


def test_state_change_schema_lists_its_fields():
    state_change = schema["components"]["schemas"]["StateChange"]

    assert set(state_change["properties"]) == {"from_state", "to_state", "note", "changed_at"}


def test_dispute_state_schema_lists_the_five_states():
    states = schema["components"]["schemas"]["DisputeState"]["enum"]

    assert set(states) == {"open", "under_review", "resolved", "rejected", "withdrawn"}
