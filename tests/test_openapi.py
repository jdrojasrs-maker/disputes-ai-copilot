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
