from typing import ClassVar


class LLMError(Exception):
    """Base error for any failure of a model call. Callers catch this, never a provider's error.

    `retryable` is a class attribute so a later retry layer can ask without building an
    instance. The message is written by the service; it never carries the API key.
    """

    retryable: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


class LLMAuthenticationError(LLMError):
    """The provider rejected the credentials or the key may not do this."""


class LLMBadRequestError(LLMError):
    """The provider rejected the request itself (malformed, unknown model, odd turn order)."""


class LLMRateLimitError(LLMError):
    retryable = True


class LLMTimeoutError(LLMError):
    retryable = True


class LLMProviderUnavailableError(LLMError):
    retryable = True


class LLMConfigurationError(Exception):
    """A setup mistake (missing or invalid setting). Not an LLMError: it is not a provider
    failure, so code that catches LLMError around a call does not swallow it."""
