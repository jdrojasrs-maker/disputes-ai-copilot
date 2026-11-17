from pathlib import Path

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from disputes.llm.errors import LLMConfigurationError


class LLMSettings(BaseSettings):
    """LLM settings, read from the environment (and a local .env file if there is one).

    Field names in upper case are the environment variable names.
    """

    # extra="ignore": the same .env file also holds variables for other parts (DATABASE_URL).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr
    llm_model: str = Field(min_length=1)
    llm_timeout_seconds: float = Field(default=60, gt=0)


def load_settings(env_file: str | Path | None = ".env") -> LLMSettings:
    """Build the settings now (never at import time).

    A missing or invalid value raises LLMConfigurationError naming the environment variable.
    The message is built from the variable name and pydantic's rule text, never from the value
    that was supplied, and the validation error is not attached as a cause.
    """
    problems: list[str] = []
    try:
        return LLMSettings(_env_file=env_file)
    except ValidationError as error:
        for detail in error.errors():
            variable = str(detail["loc"][0]).upper()
            if detail["type"] == "missing":
                problems.append(f"{variable} is not set")
            else:
                problems.append(f"{variable} is invalid: {detail['msg']}")
    raise LLMConfigurationError("; ".join(problems))
