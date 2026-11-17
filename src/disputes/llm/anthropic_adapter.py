"""Anthropic adapter for LLMClient. The only module that imports the provider SDK."""

import anthropic
from pydantic import SecretStr

from disputes.llm.errors import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from disputes.llm.models import LLMRequest, LLMResponse, StopReason, TokenUsage
from disputes.llm.settings import load_settings

_STOP_REASONS = {
    "end_turn": StopReason.COMPLETED,
    "stop_sequence": StopReason.COMPLETED,
    "max_tokens": StopReason.MAX_TOKENS,
}


def _translate(error: anthropic.AnthropicError) -> LLMError:
    """Turn a provider failure into the service's own error.

    The message is our own text plus the HTTP status. It is never str(error), because the
    provider's error holds the outgoing request, headers (and the key) included. Order
    matters: APITimeoutError is a subclass of APIConnectionError, so it is tested first.
    """
    status = getattr(error, "status_code", None)
    request_id = getattr(error, "request_id", None)
    detail = {"status_code": status, "request_id": request_id}

    if isinstance(error, anthropic.APITimeoutError | anthropic.RequestTimeoutError):
        return LLMTimeoutError(f"Anthropic call timed out{_with_status(status)}", **detail)
    if isinstance(error, anthropic.APIConnectionError):
        return LLMProviderUnavailableError("Could not connect to Anthropic", **detail)
    if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return LLMAuthenticationError(
            f"Anthropic rejected the credentials{_with_status(status)}", **detail
        )
    if isinstance(
        error,
        anthropic.BadRequestError | anthropic.NotFoundError | anthropic.UnprocessableEntityError,
    ):
        return LLMBadRequestError(f"Anthropic rejected the request{_with_status(status)}", **detail)
    if isinstance(error, anthropic.RateLimitError):
        return LLMRateLimitError(f"Anthropic rate limit reached{_with_status(status)}", **detail)
    if isinstance(error, anthropic.InternalServerError):
        return LLMProviderUnavailableError(
            f"Anthropic is unavailable{_with_status(status)}", **detail
        )
    return LLMError(f"Anthropic call failed{_with_status(status)}", **detail)


def _with_status(status: int | None) -> str:
    return f" (HTTP {status})" if status is not None else ""


class AnthropicLLMClient:
    """One attempt per call: the SDK's own automatic retries are turned off (max_retries=0)."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        http_client: anthropic.DefaultAsyncHttpxClient | None = None,
    ) -> None:
        self._model = model
        # The secret is unwrapped once, here, and handed straight to the SDK.
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key.get_secret_value(),
            max_retries=0,
            timeout=timeout_seconds,
            http_client=http_client,
        )

    @classmethod
    def from_env(cls) -> "AnthropicLLMClient":
        """Build from ANTHROPIC_API_KEY, LLM_MODEL and LLM_TIMEOUT_SECONDS (never at import)."""
        settings = load_settings()
        return cls(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    def __repr__(self) -> str:
        return f"AnthropicLLMClient(model={self._model!r})"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        arguments: dict = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        if request.system is not None:
            arguments["system"] = request.system

        translated: LLMError | None = None
        try:
            answer = await self._client.messages.create(**arguments)
        except anthropic.AnthropicError as error:
            translated = _translate(error)
        if translated is not None:
            # Raised outside the except block on purpose: inside it, Python would attach the
            # provider error (and its request, with the key) as the implicit context.
            raise translated

        # Only text blocks: with thinking on, an answer can start with a thinking block.
        text = "".join(block.text for block in answer.content if block.type == "text")
        return LLMResponse(
            text=text,
            usage=TokenUsage(
                input_tokens=answer.usage.input_tokens,
                output_tokens=answer.usage.output_tokens,
            ),
            model=answer.model,
            stop_reason=_STOP_REASONS.get(answer.stop_reason, StopReason.OTHER),
        )
