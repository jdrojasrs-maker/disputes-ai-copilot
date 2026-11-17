from typing import Protocol, runtime_checkable

from disputes.llm.models import LLMRequest, LLMResponse


@runtime_checkable
class LLMClient(Protocol):
    """The one way the service asks a language model. No provider appears in this signature."""

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
