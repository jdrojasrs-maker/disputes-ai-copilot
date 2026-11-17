import pytest
from pydantic import ValidationError

from disputes.llm.models import (
    LLMRequest,
    LLMResponse,
    Message,
    Role,
    StopReason,
    TokenUsage,
)


def make_message(content: str = "What is a chargeback?") -> Message:
    return Message(role=Role.USER, content=content)


def make_request(**overrides: object) -> LLMRequest:
    fields: dict[str, object] = {"messages": [make_message()], "max_tokens": 100}
    fields.update(overrides)
    return LLMRequest(**fields)


def make_response(**overrides: object) -> LLMResponse:
    fields: dict[str, object] = {
        "text": "A chargeback is a reversal of a card payment.",
        "usage": TokenUsage(input_tokens=12, output_tokens=9),
        "model": "test-model",
        "stop_reason": StopReason.COMPLETED,
    }
    fields.update(overrides)
    return LLMResponse(**fields)


# --- Message (FR-003) ---


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_a_message_accepts_the_user_and_assistant_roles(role: str) -> None:
    message = Message(role=role, content="hello")
    assert message.role == Role(role)


@pytest.mark.parametrize("role", ["system", "tool", "User", ""])
def test_a_message_rejects_any_other_role(role: str) -> None:
    with pytest.raises(ValidationError):
        Message(role=role, content="hello")


@pytest.mark.parametrize("content", ["", "   ", "\n", "\t \n"])
def test_a_message_rejects_empty_or_whitespace_only_text(content: str) -> None:
    with pytest.raises(ValidationError):
        Message(role=Role.USER, content=content)


def test_a_message_stores_its_text_untrimmed() -> None:
    assert make_message("  hello  ").content == "  hello  "


# --- LLMRequest (FR-004, FR-005, FR-008) ---


def test_a_request_without_a_system_prompt_is_valid_and_defaults_to_none() -> None:
    assert make_request().system is None


def test_a_request_keeps_a_given_system_prompt() -> None:
    assert make_request(system="You help with disputes.").system == "You help with disputes."


@pytest.mark.parametrize("system", ["", "  ", "\n"])
def test_a_request_rejects_an_empty_or_whitespace_system_prompt(system: str) -> None:
    with pytest.raises(ValidationError):
        make_request(system=system)


def test_a_request_rejects_an_empty_message_list() -> None:
    with pytest.raises(ValidationError):
        make_request(messages=[])


@pytest.mark.parametrize("max_tokens", [0, -1])
def test_a_request_rejects_a_max_tokens_that_is_not_positive(max_tokens: int) -> None:
    with pytest.raises(ValidationError):
        make_request(max_tokens=max_tokens)


def test_a_request_accepts_a_max_tokens_of_one() -> None:
    assert make_request(max_tokens=1).max_tokens == 1


@pytest.mark.parametrize("name", ["temperature", "top_p", "top_k"])
def test_a_request_rejects_sampling_parameters(name: str) -> None:
    with pytest.raises(ValidationError):
        make_request(**{name: 0.5})


def test_a_list_of_messages_becomes_a_tuple_and_the_callers_list_is_unchanged() -> None:
    messages = [make_message("first"), make_message("second")]
    snapshot = list(messages)

    request = make_request(messages=messages)

    assert isinstance(request.messages, tuple)
    assert list(request.messages) == snapshot
    assert messages == snapshot


# --- TokenUsage ---


def test_token_usage_accepts_zero_tokens() -> None:
    usage = TokenUsage(input_tokens=0, output_tokens=0)
    assert (usage.input_tokens, usage.output_tokens) == (0, 0)


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
def test_token_usage_rejects_negative_counts(field: str) -> None:
    counts = {"input_tokens": 1, "output_tokens": 1, field: -1}
    with pytest.raises(ValidationError):
        TokenUsage(**counts)


# --- LLMResponse and StopReason (FR-006) ---


def test_a_response_may_have_empty_text() -> None:
    assert make_response(text="").text == ""


def test_a_response_rejects_an_empty_model_name() -> None:
    with pytest.raises(ValidationError):
        make_response(model="")


def test_the_stop_reason_has_exactly_three_values() -> None:
    assert {reason.value for reason in StopReason} == {"completed", "max_tokens", "other"}


# --- Immutability (FR-006) ---


@pytest.mark.parametrize(
    ("instance", "field", "value"),
    [
        (make_message(), "content", "changed"),
        (make_request(), "max_tokens", 5),
        (TokenUsage(input_tokens=1, output_tokens=1), "input_tokens", 2),
        (make_response(), "text", "changed"),
    ],
    ids=["Message", "LLMRequest", "TokenUsage", "LLMResponse"],
)
def test_the_models_cannot_be_changed_after_they_are_built(
    instance: object, field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        setattr(instance, field, value)
