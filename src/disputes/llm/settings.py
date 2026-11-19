from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationError
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


class AzureOpenAISettings(BaseSettings):
    """Azure OpenAI settings, read from the environment (and a local .env file if there is one).

    Upper-case field names are the environment variable names. LLM_MODEL is not used here: the
    deployment name plays that role. LLM_TIMEOUT_SECONDS is the same variable as for Anthropic.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_base_url: AnyHttpUrl
    azure_openai_api_key: SecretStr
    azure_openai_deployment: str = Field(min_length=1)
    llm_timeout_seconds: float = Field(default=60, gt=0)


def load_settings(env_file: str | Path | None = ".env") -> LLMSettings:
    """Build the Anthropic settings now (never at import time).

    A missing or invalid value raises LLMConfigurationError naming the environment variable.
    """
    return _load(LLMSettings, env_file)


def load_azure_settings(env_file: str | Path | None = ".env") -> AzureOpenAISettings:
    """Build the Azure OpenAI settings now (never at import time). Same error rules."""
    return _load(AzureOpenAISettings, env_file)


def _load[SettingsT: BaseSettings](
    settings_class: type[SettingsT], env_file: str | Path | None
) -> SettingsT:
    # The message is built from the variable name and pydantic's rule text, never from the value
    # that was supplied, and the validation error is not attached as a cause.
    problems: list[str] = []
    try:
        return settings_class(_env_file=env_file)
    except ValidationError as error:
        for detail in error.errors():
            variable = str(detail["loc"][0]).upper()
            if detail["type"] == "missing":
                problems.append(f"{variable} is not set")
            else:
                problems.append(f"{variable} is invalid: {detail['msg']}")
    raise LLMConfigurationError("; ".join(problems))
