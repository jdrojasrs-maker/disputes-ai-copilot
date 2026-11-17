"""Tests of the Anthropic adapter. The real SDK runs against an in-memory HTTP transport:
no network, and the SDK's own request/response handling is exercised for real."""

import asyncio
import json
import logging
import traceback
from collections.abc import Callable
from pathlib import Path

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from disputes.llm.anthropic_adapter import AnthropicLLMClient
from disputes.llm.client import LLMClient
from disputes.llm.errors import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMConfigurationError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from disputes.llm.models import LLMRequest, Message, Role, StopReason

SENTINEL = "sk-test-SENTINEL-do-not-leak"
CONFIGURED_MODEL = "configured-model"
ANSWERING_MODEL = "answering-model"

Handler = Callable[[httpx2.Request], httpx2.Response]


class Wire:
    """Stands in for the network: records the requests the SDK sends and answers them."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self._handler(request)

    @property
    def calls(self) -> int:
        return len(self.requests)

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


def message_body(
    content: list[dict] | None = None,
    stop_reason: str | None = "end_turn",
    model: str = ANSWERING_MODEL,
    usage: tuple[int, int] = (11, 7),
) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": "Hello."}] if content is None else content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": usage[0], "output_tokens": usage[1]},
    }


def answering(**kwargs: object) -> Handler:
    return lambda request: httpx2.Response(200, json=message_body(**kwargs))


def failing_with(status: int) -> Handler:
    return lambda request: httpx2.Response(
        status,
        json={"type": "error", "error": {"type": "api_error", "message": "boom"}},
        headers={"request-id": "req_test"},
    )


def raising(error: Exception) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise error

    return handler


def build(wire: Wire, timeout_seconds: float = 30.0) -> AnthropicLLMClient:
    return AnthropicLLMClient(
        api_key=SecretStr(SENTINEL),
        model=CONFIGURED_MODEL,
        timeout_seconds=timeout_seconds,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(wire)),
    )


def make_request(text: str = "Summarize this dispute.", system: str | None = None) -> LLMRequest:
    return LLMRequest(
        system=system, messages=[Message(role=Role.USER, content=text)], max_tokens=64
    )


# ---------------------------------------------------------------------------------------
# Success path (FR-006, FR-012)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_an_answer_is_mapped_to_the_neutral_response() -> None:
    wire = Wire(answering(usage=(11, 7)))

    response = await build(wire).complete(make_request())

    assert response.text == "Hello."
    assert (response.usage.input_tokens, response.usage.output_tokens) == (11, 7)
    assert response.stop_reason is StopReason.COMPLETED
    assert wire.calls == 1


@pytest.mark.anyio
async def test_the_model_name_comes_from_the_answer_not_from_the_setting() -> None:
    wire = Wire(answering(model=ANSWERING_MODEL))

    response = await build(wire).complete(make_request())

    assert response.model == ANSWERING_MODEL
    assert wire.body()["model"] == CONFIGURED_MODEL


@pytest.mark.anyio
async def test_the_request_sent_has_the_expected_shape_and_the_key() -> None:
    wire = Wire(answering())
    request = LLMRequest(
        system="You help with disputes.",
        messages=[
            Message(role=Role.USER, content="first"),
            Message(role=Role.ASSISTANT, content="second"),
            Message(role=Role.USER, content="third"),
        ],
        max_tokens=123,
    )

    await build(wire).complete(request)

    body = wire.body()
    assert body["system"] == "You help with disputes."
    assert body["max_tokens"] == 123
    assert body["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]
    for sampling in ("temperature", "top_p", "top_k"):
        assert sampling not in body
    # Observed with anthropic 2.10.0: the key travels as a bearer token.
    assert wire.requests[0].headers["authorization"] == f"Bearer {SENTINEL}"


@pytest.mark.anyio
async def test_no_system_key_is_sent_when_there_is_no_system_prompt() -> None:
    wire = Wire(answering())

    await build(wire).complete(make_request(system=None))

    assert "system" not in wire.body()


@pytest.mark.anyio
async def test_text_blocks_are_joined_and_a_thinking_block_is_ignored() -> None:
    content = [
        {"type": "thinking", "thinking": "private reasoning", "signature": "sig"},
        {"type": "text", "text": "Part one. "},
        {"type": "text", "text": "Part two."},
    ]
    wire = Wire(answering(content=content))

    response = await build(wire).complete(make_request())

    assert response.text == "Part one. Part two."


@pytest.mark.anyio
async def test_an_answer_with_no_text_gives_empty_text() -> None:
    wire = Wire(answering(content=[]))

    response = await build(wire).complete(make_request())

    assert response.text == ""


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_value", "expected"),
    [
        ("end_turn", StopReason.COMPLETED),
        ("stop_sequence", StopReason.COMPLETED),
        ("max_tokens", StopReason.MAX_TOKENS),
        ("tool_use", StopReason.OTHER),
        ("pause_turn", StopReason.OTHER),
        ("refusal", StopReason.OTHER),
        (None, StopReason.OTHER),
    ],
)
async def test_the_providers_stop_reason_is_mapped_to_the_neutral_one(
    provider_value: str | None, expected: StopReason
) -> None:
    wire = Wire(answering(stop_reason=provider_value))

    response = await build(wire).complete(make_request())

    assert response.stop_reason is expected


@pytest.mark.anyio
async def test_a_cut_off_answer_is_returned_not_raised() -> None:
    content = [{"type": "text", "text": "Half an ans"}]
    wire = Wire(answering(content=content, stop_reason="max_tokens"))

    response = await build(wire).complete(make_request())

    assert response.text == "Half an ans"
    assert response.stop_reason is StopReason.MAX_TOKENS


# ---------------------------------------------------------------------------------------
# The adapter keeps no state and does not touch what it is given (FR-008)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_request_is_not_modified_by_the_call() -> None:
    wire = Wire(answering())
    request = make_request(system="Be brief.")
    before = request.model_copy(deep=True)

    await build(wire).complete(request)

    assert request == before


@pytest.mark.anyio
async def test_two_concurrent_calls_each_get_their_own_answer() -> None:
    def echo(request: httpx2.Request) -> httpx2.Response:
        last = json.loads(request.content)["messages"][-1]["content"]
        return httpx2.Response(200, json=message_body(content=[{"type": "text", "text": last}]))

    client = build(Wire(echo))

    first, second = await asyncio.gather(
        client.complete(make_request("question A")), client.complete(make_request("question B"))
    )

    assert (first.text, second.text) == ("question A", "question B")


# ---------------------------------------------------------------------------------------
# Swapping the client changes nothing for the caller (SC-008)
# ---------------------------------------------------------------------------------------


async def ask(client: LLMClient, question: str) -> str:
    """A caller written only against the interface."""
    response = await client.complete(make_request(question))
    return response.text


@pytest.mark.anyio
async def test_a_caller_works_the_same_with_the_fake_and_with_the_adapter() -> None:
    from disputes.llm.models import LLMResponse, TokenUsage
    from fake_llm import FakeLLMClient

    fake = FakeLLMClient().will_return(
        LLMResponse(
            text="Hello.",
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            model="fake",
            stop_reason=StopReason.COMPLETED,
        )
    )
    adapter = build(Wire(answering()))

    assert await ask(fake, "hi") == await ask(adapter, "hi") == "Hello."
    assert isinstance(adapter, LLMClient)


# ---------------------------------------------------------------------------------------
# Failure translation (US3, FR-009, FR-010)
# ---------------------------------------------------------------------------------------

STATUS_TO_ERROR: list[tuple[int, type[LLMError]]] = [
    (401, LLMAuthenticationError),
    (403, LLMAuthenticationError),
    (400, LLMBadRequestError),
    (404, LLMBadRequestError),
    (422, LLMBadRequestError),
    (429, LLMRateLimitError),
    (408, LLMTimeoutError),
    (500, LLMProviderUnavailableError),
    (502, LLMProviderUnavailableError),
    (503, LLMProviderUnavailableError),
    (529, LLMProviderUnavailableError),
    (409, LLMError),
    (418, LLMError),
]


@pytest.mark.anyio
@pytest.mark.parametrize(("status", "expected"), STATUS_TO_ERROR)
async def test_an_http_failure_is_translated_to_the_matching_service_error(
    status: int, expected: type[LLMError]
) -> None:
    wire = Wire(failing_with(status))

    with pytest.raises(LLMError) as raised:
        await build(wire).complete(make_request())

    error = raised.value
    assert type(error) is expected
    assert error.status_code == status
    assert error.request_id == "req_test"
    assert str(status) in str(error)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("transport_error", "expected"),
    [
        (httpx2.ReadTimeout("too slow"), LLMTimeoutError),
        (httpx2.ConnectError("no route"), LLMProviderUnavailableError),
    ],
    ids=["timeout", "connection"],
)
async def test_a_transport_failure_is_translated_to_the_matching_service_error(
    transport_error: Exception, expected: type[LLMError]
) -> None:
    wire = Wire(raising(transport_error))

    with pytest.raises(LLMError) as raised:
        await build(wire).complete(make_request())

    assert type(raised.value) is expected
    assert raised.value.status_code is None
    assert raised.value.retryable is True


@pytest.mark.anyio
async def test_the_retryable_flag_follows_the_kind_of_failure() -> None:
    expected = {
        401: False,
        400: False,
        429: True,
        408: True,
        503: True,
        418: False,
    }
    for status, retryable in expected.items():
        with pytest.raises(LLMError) as raised:
            await build(Wire(failing_with(status))).complete(make_request())
        assert raised.value.retryable is retryable, status


@pytest.mark.anyio
async def test_the_provider_error_is_not_attached_to_the_service_error() -> None:
    with pytest.raises(LLMError) as raised:
        await build(Wire(failing_with(500))).complete(make_request())

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


# ---------------------------------------------------------------------------------------
# One attempt only (FR-013, SC-005) and the timeout (FR-015)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "handler",
    [
        failing_with(500),
        failing_with(429),
        failing_with(529),
        raising(httpx2.ReadTimeout("too slow")),
        raising(httpx2.ConnectError("no route")),
    ],
    ids=["500", "429", "529", "timeout", "connection"],
)
async def test_a_failing_call_is_attempted_exactly_once(handler: Handler) -> None:
    wire = Wire(handler)

    with pytest.raises(LLMError):
        await build(wire).complete(make_request())

    assert wire.calls == 1


def test_the_sdk_client_is_built_with_retries_off_and_the_configured_timeout() -> None:
    client = build(Wire(answering()), timeout_seconds=12.5)

    assert client._client.max_retries == 0
    assert client._client.timeout == 12.5


# ---------------------------------------------------------------------------------------
# The key never leaks (FR-016, SC-004)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    "handler",
    [
        failing_with(401),
        failing_with(400),
        failing_with(429),
        failing_with(500),
        failing_with(418),
        raising(httpx2.ReadTimeout("too slow")),
        raising(httpx2.ConnectError("no route")),
    ],
    ids=["401", "400", "429", "500", "418", "timeout", "connection"],
)
async def test_the_key_is_in_no_error_text_no_traceback_and_no_log(
    handler: Handler, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = build(Wire(handler))

    with pytest.raises(LLMError) as raised:
        await client.complete(make_request())

    error = raised.value
    rendered = "".join(traceback.format_exception(error))
    for text in (str(error), repr(error), rendered, repr(client), str(client), caplog.text):
        assert SENTINEL not in text


# ---------------------------------------------------------------------------------------
# Building from the environment (FR-017)
# ---------------------------------------------------------------------------------------


def test_from_env_builds_the_adapter_when_everything_is_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # so no local .env file is read
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    monkeypatch.setenv("LLM_MODEL", CONFIGURED_MODEL)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "9")

    client = AnthropicLLMClient.from_env()

    assert isinstance(client, LLMClient)
    assert client._client.timeout == 9


def test_from_env_without_a_key_names_the_missing_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", CONFIGURED_MODEL)

    with pytest.raises(LLMConfigurationError, match="ANTHROPIC_API_KEY"):
        AnthropicLLMClient.from_env()
