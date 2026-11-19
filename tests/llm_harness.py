"""One way to drive every LLMClient implementation from the same shared tests.

Each harness holds a client and can be told, in the provider's own terms, what the next call
should do: answer, or fail in one of the service's failure kinds. No network is involved: the
adapters run their real SDK against an in-memory HTTP transport.
"""

import json
from collections.abc import Callable

import anthropic
import httpx2
import openai
from pydantic import SecretStr

from disputes.llm.anthropic_adapter import AnthropicLLMClient
from disputes.llm.azure_openai_adapter import AzureOpenAILLMClient
from disputes.llm.client import LLMClient
from disputes.llm.errors import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from disputes.llm.models import LLMRequest, LLMResponse, StopReason, TokenUsage
from fake_llm import FakeLLMClient

KEY = "harness-test-SENTINEL-do-not-leak"

# The six failure kinds of the service, and the error each must become.
FAILURE_KINDS: dict[str, type[LLMError]] = {
    "authentication": LLMAuthenticationError,
    "bad_request": LLMBadRequestError,
    "rate_limit": LLMRateLimitError,
    "timeout": LLMTimeoutError,
    "unavailable": LLMProviderUnavailableError,
    "other": LLMError,
}

# What an HTTP provider answers for each kind. "timeout" is not an answer: the transport raises.
_STATUS = {
    "authentication": 401,
    "bad_request": 400,
    "rate_limit": 429,
    "unavailable": 503,
    "other": 418,
}

Handler = Callable[[httpx2.Request], httpx2.Response]


class _EchoClient:
    """An LLMClient that answers with the text of the last message it was given."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=request.messages[-1].content,
            usage=TokenUsage(input_tokens=1, output_tokens=1),
            model="echo",
            stop_reason=StopReason.COMPLETED,
        )


class FakeHarness:
    def __init__(self) -> None:
        self._fake = FakeLLMClient()
        self.client: LLMClient = self._fake

    @property
    def calls(self) -> int:
        return len(self._fake.calls)

    def script_answer(
        self, text: str, usage: tuple[int, int], model: str, stop: StopReason
    ) -> None:
        self._fake.will_return(
            LLMResponse(
                text=text,
                usage=TokenUsage(input_tokens=usage[0], output_tokens=usage[1]),
                model=model,
                stop_reason=stop,
            )
        )

    def script_failure(self, kind: str) -> None:
        self._fake.will_fail(FAILURE_KINDS[kind]("scripted failure"))

    def script_echo(self) -> None:
        self.client = _EchoClient()


class _HttpHarness:
    """Shared part of the adapter harnesses: a recording transport with a swappable handler."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self._handler: Handler = lambda request: httpx2.Response(500)
        self.transport = httpx2.MockTransport(self._send)
        self.client: LLMClient

    def _send(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self._handler(request)

    @property
    def calls(self) -> int:
        return len(self.requests)

    def last_body(self) -> dict:
        return json.loads(self.requests[-1].content)

    def script_failure(self, kind: str) -> None:
        if kind == "timeout":

            def handler(request: httpx2.Request) -> httpx2.Response:
                raise httpx2.ReadTimeout("too slow")

            self._handler = handler
        else:
            status = _STATUS[kind]
            body = self._failure_body()
            self._handler = lambda request: httpx2.Response(status, json=body)

    def script_answer(
        self, text: str, usage: tuple[int, int], model: str, stop: StopReason
    ) -> None:
        body = self._answer_body(text, usage, model, stop)
        self._handler = lambda request: httpx2.Response(200, json=body)

    def script_echo(self) -> None:
        """Answer every call with the text of the last message in that call's own request."""

        def handler(request: httpx2.Request) -> httpx2.Response:
            last = json.loads(request.content)["messages"][-1]["content"]
            body = self._answer_body(last, (1, 1), "echo", StopReason.COMPLETED)
            return httpx2.Response(200, json=body)

        self._handler = handler

    def _answer_body(
        self, text: str, usage: tuple[int, int], model: str, stop: StopReason
    ) -> dict:
        raise NotImplementedError

    def _failure_body(self) -> dict:
        raise NotImplementedError


class AnthropicHarness(_HttpHarness):
    _STOP = {
        StopReason.COMPLETED: "end_turn",
        StopReason.MAX_TOKENS: "max_tokens",
        StopReason.OTHER: "refusal",
    }

    def __init__(self) -> None:
        super().__init__()
        self.client = AnthropicLLMClient(
            api_key=SecretStr(KEY),
            model="configured-model",
            timeout_seconds=30,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=self.transport),
        )

    def _answer_body(
        self, text: str, usage: tuple[int, int], model: str, stop: StopReason
    ) -> dict:
        body = {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": text}],
            "stop_reason": self._STOP[stop],
            "stop_sequence": None,
            "usage": {"input_tokens": usage[0], "output_tokens": usage[1]},
        }
        return body

    def _failure_body(self) -> dict:
        return {"type": "error", "error": {"type": "api_error", "message": "boom"}}


class AzureHarness(_HttpHarness):
    _STOP = {
        StopReason.COMPLETED: "stop",
        StopReason.MAX_TOKENS: "length",
        StopReason.OTHER: "content_filter",
    }

    def __init__(self) -> None:
        super().__init__()
        self.client = AzureOpenAILLMClient(
            api_key=SecretStr(KEY),
            base_url="https://example-resource.openai.azure.com/openai/v1/",
            deployment="configured-deployment",
            timeout_seconds=30,
            http_client=openai.DefaultAsyncHttpxClient(transport=self.transport),
        )

    def _answer_body(
        self, text: str, usage: tuple[int, int], model: str, stop: StopReason
    ) -> dict:
        body = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": self._STOP[stop],
                    "message": {"role": "assistant", "content": text},
                }
            ],
            "usage": {
                "prompt_tokens": usage[0],
                "completion_tokens": usage[1],
                "total_tokens": usage[0] + usage[1],
            },
        }
        return body

    def _failure_body(self) -> dict:
        return {"error": {"message": "boom", "type": "server_error"}}


# Used by the shared tests as the parameters of the `harness` fixture.
HARNESSES = {"fake": FakeHarness, "anthropic": AnthropicHarness, "azure": AzureHarness}
