"""Azure OpenAI adapter for LLMClient. The only module that imports the `openai` SDK."""

import openai
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

# The provider's finish_reason, in neutral terms. Anything not listed (content_filter,
# tool_calls, ...) is "other".
_STOP_REASONS = {
    "stop": StopReason.COMPLETED,
    "length": StopReason.MAX_TOKENS,
}


def _translate(error: openai.OpenAIError) -> LLMError:
    """Turn a provider failure into the service's own error.

    The message is our own text plus the HTTP status. It is never str(error), because the
    provider's error holds the provider's text and its request (headers, and the key). Order
    matters: APITimeoutError is a subclass of APIConnectionError, so it is tested first.
    """
    status = getattr(error, "status_code", None)
    detail = {"status_code": status, "request_id": getattr(error, "request_id", None)}

    # The SDK has no class for 408: it arrives as a plain APIStatusError.
    if isinstance(error, openai.APITimeoutError) or status == 408:
        return LLMTimeoutError(f"Azure OpenAI call timed out{_with_status(status)}", **detail)
    if isinstance(error, openai.APIConnectionError):
        return LLMProviderUnavailableError("Could not connect to Azure OpenAI", **detail)
    if isinstance(error, openai.AuthenticationError | openai.PermissionDeniedError):
        return LLMAuthenticationError(
            f"Azure OpenAI rejected the credentials{_with_status(status)}", **detail
        )
    if isinstance(
        error,
        openai.BadRequestError | openai.NotFoundError | openai.UnprocessableEntityError,
    ):
        return LLMBadRequestError(
            f"Azure OpenAI rejected the request{_with_status(status)}", **detail
        )
    if isinstance(error, openai.RateLimitError):
        return LLMRateLimitError(
            f"Azure OpenAI rate limit reached{_with_status(status)}", **detail
        )
    if isinstance(error, openai.InternalServerError):
        return LLMProviderUnavailableError(
            f"Azure OpenAI is unavailable{_with_status(status)}", **detail
        )
    return LLMError(f"Azure OpenAI call failed{_with_status(status)}", **detail)


def _with_status(status: int | None) -> str:
    return f" (HTTP {status})" if status is not None else ""


class AzureOpenAILLMClient:
    """One attempt per call: the SDK's own automatic retries are turned off (max_retries=0)."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        deployment: str,
        timeout_seconds: float,
        http_client: openai.DefaultAsyncHttpxClient | None = None,
    ) -> None:
        self._deployment = deployment
        # The secret is unwrapped once, here, and handed straight to the SDK.
        self._client = openai.AsyncOpenAI(
            api_key=api_key.get_secret_value(),
            base_url=base_url,
            max_retries=0,
            timeout=timeout_seconds,
            http_client=http_client,
        )

    def __repr__(self) -> str:
        return f"AzureOpenAILLMClient(deployment={self._deployment!r})"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages: list[dict] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.extend(
            {"role": message.role.value, "content": message.content}
            for message in request.messages
        )

        translated: LLMError | None = None
        try:
            answer = await self._client.chat.completions.create(
                # Azure takes the deployment name here, not a model id.
                model=self._deployment,
                messages=messages,
                # Azure rejects max_tokens for these models; it wants max_completion_tokens.
                max_completion_tokens=request.max_tokens,
            )
        except openai.OpenAIError as error:
            translated = _translate(error)
        if translated is not None:
            # Raised outside the except block on purpose: inside it, Python would attach the
            # provider error (and its request, with the key) as the implicit context.
            raise translated

        # An answer with no text (for example blocked by the content filter) is an error,
        # never an empty response. The messages are fixed text: nothing from the provider.
        text = answer.choices[0].message.content if answer.choices else None
        if text is None or not text.strip():
            raise LLMError("Azure OpenAI returned no text")
        if answer.usage is None:
            raise LLMError("Azure OpenAI returned no token usage")

        choice = answer.choices[0]
        return LLMResponse(
            text=text,
            usage=TokenUsage(
                input_tokens=answer.usage.prompt_tokens,
                output_tokens=answer.usage.completion_tokens,
            ),
            # The versioned name the service reports; it differs from the deployment name.
            model=answer.model,
            stop_reason=_STOP_REASONS.get(choice.finish_reason, StopReason.OTHER),
        )
