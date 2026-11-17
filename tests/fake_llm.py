"""A scriptable test double for LLMClient: no network, no key, no real model."""

from collections import deque
from typing import Self

from disputes.llm.errors import LLMError
from disputes.llm.models import LLMRequest, LLMResponse


class FakeScriptExhaustedError(Exception):
    """The fake was called more times than it has scripted answers.

    Deliberately not an LLMError: code under test that catches provider failures must not
    swallow a badly written test script.
    """


class FakeLLMClient:
    """Returns scripted answers in order and records every request it receives."""

    def __init__(self) -> None:
        self._script: deque[LLMResponse | LLMError] = deque()
        self.calls: list[LLMRequest] = []

    def will_return(self, response: LLMResponse) -> Self:
        self._script.append(response)
        return self

    def will_fail(self, error: LLMError) -> Self:
        self._script.append(error)
        return self

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if not self._script:
            raise FakeScriptExhaustedError(
                f"call {len(self.calls)} has no scripted answer; "
                "add one with will_return(...) or will_fail(...)"
            )
        item = self._script.popleft()
        if isinstance(item, LLMError):
            raise item
        return item
