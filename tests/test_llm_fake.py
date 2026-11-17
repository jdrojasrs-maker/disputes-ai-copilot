import socket

import pytest

from disputes.llm.client import LLMClient
from disputes.llm.errors import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from disputes.llm.models import (
    LLMRequest,
    LLMResponse,
    Message,
    Role,
    StopReason,
    TokenUsage,
)
from fake_llm import FakeLLMClient, FakeScriptExhaustedError

ALL_ERROR_KINDS = [
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMProviderUnavailableError,
    LLMError,
]


def make_request(text: str = "Summarize this dispute.") -> LLMRequest:
    return LLMRequest(messages=[Message(role=Role.USER, content=text)], max_tokens=50)


def make_response(text: str = "A short summary.") -> LLMResponse:
    return LLMResponse(
        text=text,
        usage=TokenUsage(input_tokens=5, output_tokens=4),
        model="fake-model",
        stop_reason=StopReason.COMPLETED,
    )


@pytest.mark.anyio
async def test_scripted_responses_come_back_in_order() -> None:
    fake = FakeLLMClient()
    fake.will_return(make_response("first")).will_return(make_response("second"))

    first = await fake.complete(make_request())
    second = await fake.complete(make_request())

    assert (first.text, second.text) == ("first", "second")


@pytest.mark.anyio
async def test_every_request_is_recorded_in_order() -> None:
    fake = FakeLLMClient()
    fake.will_return(make_response()).will_return(make_response())
    first, second = make_request("one"), make_request("two")

    await fake.complete(first)
    await fake.complete(second)

    assert fake.calls == [first, second]


@pytest.mark.anyio
@pytest.mark.parametrize("error_class", ALL_ERROR_KINDS)
async def test_a_scripted_failure_is_raised_as_that_exact_class(
    error_class: type[LLMError],
) -> None:
    fake = FakeLLMClient()
    fake.will_fail(error_class("simulated"))

    with pytest.raises(LLMError) as raised:
        await fake.complete(make_request())

    assert type(raised.value) is error_class
    assert str(raised.value) == "simulated"


@pytest.mark.anyio
async def test_responses_and_failures_can_be_mixed_in_one_script() -> None:
    fake = FakeLLMClient()
    fake.will_return(make_response("ok")).will_fail(LLMRateLimitError("slow down"))
    fake.will_return(make_response("ok again"))

    assert (await fake.complete(make_request())).text == "ok"
    with pytest.raises(LLMRateLimitError):
        await fake.complete(make_request())
    assert (await fake.complete(make_request())).text == "ok again"
    assert len(fake.calls) == 3


@pytest.mark.anyio
async def test_an_empty_script_fails_clearly_instead_of_inventing_an_answer() -> None:
    fake = FakeLLMClient()

    with pytest.raises(FakeScriptExhaustedError):
        await fake.complete(make_request())


def test_running_out_of_script_is_not_an_llm_error() -> None:
    # Code under test that catches LLMError must not swallow a badly written test script.
    assert not issubclass(FakeScriptExhaustedError, LLMError)


def test_the_fake_is_an_llm_client() -> None:
    assert isinstance(FakeLLMClient(), LLMClient)


@pytest.mark.anyio
async def test_the_request_is_not_modified_by_the_call() -> None:
    fake = FakeLLMClient()
    fake.will_return(make_response())
    request = make_request()
    before = request.model_copy(deep=True)

    await fake.complete(request)

    assert request == before


@pytest.mark.anyio
async def test_the_fake_uses_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the fake must not create sockets")

    monkeypatch.setattr(socket, "socket", refuse)
    fake = FakeLLMClient()
    fake.will_return(make_response())

    assert (await fake.complete(make_request())).text == "A short summary."


@pytest.mark.anyio
async def test_the_fixture_gives_a_working_fake(fake_llm: FakeLLMClient) -> None:
    fake_llm.will_return(make_response())

    await fake_llm.complete(make_request())

    assert len(fake_llm.calls) == 1


def test_the_fixture_gives_a_fresh_fake_to_every_test(fake_llm: FakeLLMClient) -> None:
    # The test above used the fixture and made a call; this one must not see it.
    assert fake_llm.calls == []
