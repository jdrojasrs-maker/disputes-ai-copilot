"""Provider-neutral access to a language model.

The Anthropic adapter is deliberately not imported here: import
`disputes.llm.anthropic_adapter` explicitly, so merely importing this package never loads the
provider SDK.
"""

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
from disputes.llm.models import (
    LLMRequest,
    LLMResponse,
    Message,
    Role,
    StopReason,
    TokenUsage,
)
from disputes.llm.settings import LLMSettings, load_settings

__all__ = [
    "LLMAuthenticationError",
    "LLMBadRequestError",
    "LLMClient",
    "LLMConfigurationError",
    "LLMError",
    "LLMProviderUnavailableError",
    "LLMRateLimitError",
    "LLMRequest",
    "LLMResponse",
    "LLMSettings",
    "LLMTimeoutError",
    "Message",
    "Role",
    "StopReason",
    "TokenUsage",
    "load_settings",
]
