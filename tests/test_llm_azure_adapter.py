"""Tests of the Azure OpenAI adapter. The real SDK runs against an in-memory HTTP transport:
no network, and the SDK's own request/response handling is exercised for real."""

import json
import logging
import traceback
from collections.abc import Callable

import httpx2
import openai
import pytest
from pydantic import SecretStr

from disputes.llm.azure_openai_adapter import AzureOpenAILLMClient
from disputes.llm.errors import LLMError
from disputes.llm.models import LLMRequest, Message, Role, StopReason

SENTINEL = "azure-test-SENTINEL-do-not-leak"
BASE_URL = "https://example-resource.openai.azure.com/openai/v1/"
DEPLOYMENT = "configured-deployment"
ANSWERING_MODEL = "answering-model-2026-01-01"

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


def completion_body(
    text: str | None = "Hello.",
    finish_reason: str = "stop",
    model: str = ANSWERING_MODEL,
    usage: tuple[int, int] = (11, 7),
    reasoning_tokens: int = 0,
) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": text},
            }
        ],
        "usage": {
            "prompt_tokens": usage[0],
            "completion_tokens": usage[1],
            "total_tokens": usage[0] + usage[1],
            "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
        },
    }


def answering(**kwargs: object) -> Handler:
    return lambda request: httpx2.Response(200, json=completion_body(**kwargs))


def build(wire: Wire, timeout_seconds: float = 30.0) -> AzureOpenAILLMClient:
    return AzureOpenAILLMClient(
        api_key=SecretStr(SENTINEL),
        base_url=BASE_URL,
        deployment=DEPLOYMENT,
        timeout_seconds=timeout_seconds,
        http_client=openai.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(wire)),
    )


def make_request(text: str = "Summarize this dispute.", system: str | None = None) -> LLMRequest:
    return LLMRequest(
        system=system, messages=[Message(role=Role.USER, content=text)], max_tokens=64
    )


# ---------------------------------------------------------------------------------------
# Test 5: the request Azure receives (FR-005, FR-006, FR-018)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_request_sent_asks_for_max_completion_tokens_and_names_the_deployment() -> None:
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
    # Azure rejected max_tokens with HTTP 400; it wants max_completion_tokens.
    assert body["max_completion_tokens"] == 123
    assert "max_tokens" not in body
    # The model field takes the deployment name, not a model id.
    assert body["model"] == DEPLOYMENT
    assert body["messages"] == [
        {"role": "system", "content": "You help with disputes."},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]
    for sampling in ("temperature", "top_p", "top_k"):
        assert sampling not in body
    # Observed with openai 3.55.1: the key travels as a bearer token.
    assert wire.requests[0].headers["authorization"] == f"Bearer {SENTINEL}"

    # Without a system prompt, no system message is sent.
    await build(wire).complete(make_request(system=None))
    assert [message["role"] for message in wire.body(1)["messages"]] == ["user"]


# ---------------------------------------------------------------------------------------
# Test 6: what Azure answers, in neutral terms (FR-003, FR-004)
# ---------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_value", "expected"),
    [
        ("stop", StopReason.COMPLETED),
        ("length", StopReason.MAX_TOKENS),
        ("content_filter", StopReason.OTHER),
        ("tool_calls", StopReason.OTHER),
    ],
)
async def test_the_providers_finish_reason_is_mapped_to_the_neutral_one(
    provider_value: str, expected: StopReason
) -> None:
    wire = Wire(answering(text="Half an ans", finish_reason=provider_value, usage=(11, 7),
                          reasoning_tokens=5))

    response = await build(wire).complete(make_request())

    assert response.stop_reason is expected
    # A cut-off answer is returned, not raised.
    assert response.text == "Half an ans"
    assert response.usage.input_tokens == 11
    # Reasoning tokens are reported separately by the provider; output tokens are the provider's
    # completion tokens, with no adjustment.
    assert response.usage.output_tokens == 7
    # The versioned name the service reports, not the deployment name.
    assert response.model == ANSWERING_MODEL


# ---------------------------------------------------------------------------------------
# Failures (FR-009, FR-010, FR-011, FR-014)
# ---------------------------------------------------------------------------------------


def failing_with(status: int) -> Handler:
    return lambda request: httpx2.Response(
        status, json={"error": {"message": "PROVIDER-TEXT-boom", "type": "server_error"}}
    )


def raising(error: Exception) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise error

    return handler


def with_body(body: dict) -> Handler:
    return lambda request: httpx2.Response(200, json=body)


def no_choices() -> dict:
    return {**completion_body(), "choices": []}


def filtered() -> dict:
    body = completion_body(text=None, finish_reason="content_filter")
    body["choices"][0]["message"]["refusal"] = "PROVIDER-TEXT-blocked"
    return body


def blank() -> dict:
    return completion_body(text="   ")


def no_usage() -> dict:
    body = completion_body()
    del body["usage"]
    return body


# Test 7: an answer with no text (or no usage) is an error, never an empty response (FR-010).
@pytest.mark.anyio
@pytest.mark.parametrize(
    "body", [no_choices(), filtered(), blank(), no_usage()],
    ids=["no-choices", "content-filter", "blank-text", "no-usage"],
)
async def test_an_answer_without_text_or_usage_raises_the_base_error(body: dict) -> None:
    with pytest.raises(LLMError) as raised:
        await build(Wire(with_body(body))).complete(make_request())

    error = raised.value
    assert type(error) is LLMError
    assert error.retryable is False
    assert "PROVIDER-TEXT" not in str(error)


# Test 8: one attempt only, and the SDK client has retries off (FR-011, FR-014).
@pytest.mark.anyio
@pytest.mark.parametrize(
    "handler",
    [
        failing_with(500),
        failing_with(429),
        raising(httpx2.ReadTimeout("too slow")),
        raising(httpx2.ConnectError("no route")),
    ],
    ids=["500", "429", "timeout", "connection"],
)
async def test_a_failing_call_is_attempted_exactly_once(handler: Handler) -> None:
    wire = Wire(handler)
    client = build(wire, timeout_seconds=12.5)
    assert client._client.max_retries == 0
    assert client._client.timeout == 12.5

    with pytest.raises(LLMError):
        await client.complete(make_request())

    assert wire.calls == 1


# Test 9: the key and the provider's text never leave the adapter (FR-009).
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
        with_body(filtered()),
    ],
    ids=["401", "400", "429", "500", "418", "timeout", "connection", "no-text"],
)
async def test_the_key_and_the_provider_text_are_in_no_error_traceback_or_log(
    handler: Handler, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = build(Wire(handler))

    with pytest.raises(LLMError) as raised:
        await client.complete(make_request())

    error = raised.value
    # Neither the provider error nor its request (which holds the key) hangs from ours.
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    for text in (str(error), repr(error), rendered, repr(client), caplog.text):
        assert SENTINEL not in text
        assert "PROVIDER-TEXT" not in text
