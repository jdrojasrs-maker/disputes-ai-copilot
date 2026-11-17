import pytest

from disputes.llm.errors import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMConfigurationError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)

SPECIFIC_ERRORS = [
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMProviderUnavailableError,
]


@pytest.mark.parametrize("error_class", SPECIFIC_ERRORS)
def test_every_specific_error_is_an_llm_error(error_class: type[LLMError]) -> None:
    assert issubclass(error_class, LLMError)
    assert isinstance(error_class("boom"), LLMError)


@pytest.mark.parametrize(
    ("error_class", "retryable"),
    [
        (LLMRateLimitError, True),
        (LLMTimeoutError, True),
        (LLMProviderUnavailableError, True),
        (LLMAuthenticationError, False),
        (LLMBadRequestError, False),
        (LLMError, False),
    ],
)
def test_each_error_declares_whether_it_is_retryable(
    error_class: type[LLMError], retryable: bool
) -> None:
    # Read on the class: a retry layer must be able to ask without building an instance.
    assert error_class.retryable is retryable


@pytest.mark.parametrize("error_class", [LLMError, *SPECIFIC_ERRORS])
def test_an_error_carries_its_message_and_optional_diagnosis(
    error_class: type[LLMError],
) -> None:
    plain = error_class("something failed")
    assert str(plain) == "something failed"
    assert plain.status_code is None
    assert plain.request_id is None

    detailed = error_class("something failed", status_code=429, request_id="req_123")
    assert detailed.status_code == 429
    assert detailed.request_id == "req_123"


def test_catching_the_base_error_catches_every_specific_error() -> None:
    for error_class in SPECIFIC_ERRORS:
        with pytest.raises(LLMError):
            raise error_class("boom")


def test_a_configuration_error_is_not_a_provider_error() -> None:
    assert not issubclass(LLMConfigurationError, LLMError)


def test_catching_llm_error_does_not_swallow_a_configuration_error() -> None:
    with pytest.raises(LLMConfigurationError):
        try:
            raise LLMConfigurationError("ANTHROPIC_API_KEY is not set")
        except LLMError:  # pragma: no cover - must not be reached
            pytest.fail("LLMError must not catch a configuration error")
