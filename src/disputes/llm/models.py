from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class StopReason(StrEnum):
    """Why the model stopped, in provider-neutral terms."""

    COMPLETED = "completed"
    MAX_TOKENS = "max_tokens"
    OTHER = "other"


class _FrozenModel(BaseModel):
    # frozen: a value cannot change after it is built. forbid: an unknown field (for example
    # temperature, top_p or top_k) is an error instead of being silently ignored.
    model_config = ConfigDict(frozen=True, extra="forbid")


def _reject_blank(value: str) -> str:
    # Checks the trimmed text but returns the original, so the client never alters what it sends.
    if not value.strip():
        raise ValueError("must not be empty or whitespace-only")
    return value


class Message(_FrozenModel):
    role: Role
    content: str

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, value: str) -> str:
        return _reject_blank(value)


class LLMRequest(_FrozenModel):
    system: str | None = None
    # A tuple, not a list: nobody can append to it after the request is built, and the
    # caller's own list is copied, never modified.
    messages: tuple[Message, ...] = Field(min_length=1)
    max_tokens: int = Field(gt=0)

    @field_validator("system")
    @classmethod
    def _system_not_blank(cls, value: str | None) -> str | None:
        return value if value is None else _reject_blank(value)


class TokenUsage(_FrozenModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class LLMResponse(_FrozenModel):
    text: str
    usage: TokenUsage
    model: str = Field(min_length=1)
    stop_reason: StopReason
