"""Behavior every LLMClient implementation must share: the fake, the Anthropic adapter and the
Azure OpenAI adapter run the same tests, with no network."""

import asyncio

import pytest

from disputes.llm.client import LLMClient
from disputes.llm.errors import LLMError
from disputes.llm.models import LLMRequest, Message, Role, StopReason
from llm_harness import FAILURE_KINDS, HARNESSES


@pytest.fixture(params=list(HARNESSES), ids=list(HARNESSES))
def harness(request: pytest.FixtureRequest):
    return HARNESSES[request.param]()


def make_request(text: str = "Summarize this dispute.", system: str | None = None) -> LLMRequest:
    return LLMRequest(
        system=system, messages=[Message(role=Role.USER, content=text)], max_tokens=64
    )


# Test 1: an answer comes back as the neutral response.
@pytest.mark.anyio
async def test_an_answer_comes_back_as_the_neutral_response(harness) -> None:
    harness.script_answer("Hello.", (11, 7), "answering-model", StopReason.COMPLETED)

    response = await harness.client.complete(make_request(system="Be brief."))

    assert isinstance(harness.client, LLMClient)
    assert response.text == "Hello."
    assert (response.usage.input_tokens, response.usage.output_tokens) == (11, 7)
    assert response.model == "answering-model"
    assert response.stop_reason is StopReason.COMPLETED


# Test 2: an answer cut by the token limit is returned, not raised.
@pytest.mark.anyio
async def test_an_answer_cut_by_the_token_limit_is_returned_not_raised(harness) -> None:
    harness.script_answer("Half an ans", (11, 64), "answering-model", StopReason.MAX_TOKENS)

    response = await harness.client.complete(make_request())

    assert response.text == "Half an ans"
    assert response.stop_reason is StopReason.MAX_TOKENS


# Test 3: a call does not modify the request and keeps nothing between calls.
@pytest.mark.anyio
async def test_a_call_does_not_modify_the_request_and_calls_do_not_mix(harness) -> None:
    harness.script_echo()
    request = make_request(system="Be brief.")
    before = request.model_copy(deep=True)

    await harness.client.complete(request)
    first, second = await asyncio.gather(
        harness.client.complete(make_request("question A")),
        harness.client.complete(make_request("question B")),
    )

    assert request == before
    assert (first.text, second.text) == ("question A", "question B")


# Whether a failure is worth retrying later is part of the contract, not of one provider.
RETRYABLE = {
    "authentication": False,
    "bad_request": False,
    "rate_limit": True,
    "timeout": True,
    "unavailable": True,
    "other": False,
}


@pytest.mark.anyio
@pytest.mark.parametrize("kind", list(FAILURE_KINDS))
async def test_each_failure_kind_becomes_the_matching_service_error(harness, kind: str) -> None:
    harness.script_failure(kind)

    with pytest.raises(LLMError) as raised:
        await harness.client.complete(make_request())

    assert type(raised.value) is FAILURE_KINDS[kind]
    assert raised.value.retryable is RETRYABLE[kind]
