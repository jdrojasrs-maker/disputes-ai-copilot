import os
import subprocess
import sys
from pathlib import Path

import pytest

from disputes.llm.errors import LLMConfigurationError
from disputes.llm.settings import load_settings

SENTINEL = "sk-test-SENTINEL-do-not-leak"
REPO_ROOT = Path(__file__).resolve().parent.parent
LLM_VARIABLES = ("ANTHROPIC_API_KEY", "LLM_MODEL", "LLM_TIMEOUT_SECONDS")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in LLM_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def set_valid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    monkeypatch.setenv("LLM_MODEL", "test-model")


# --- loading (FR-014) ---


def test_values_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12.5")

    settings = load_settings(env_file=None)

    assert settings.anthropic_api_key.get_secret_value() == SENTINEL
    assert settings.llm_model == "test-model"
    assert settings.llm_timeout_seconds == 12.5


def test_the_timeout_defaults_to_60_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)

    assert load_settings(env_file=None).llm_timeout_seconds == 60


def test_values_can_come_from_an_env_file_and_unknown_variables_are_ignored(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"ANTHROPIC_API_KEY={SENTINEL}\nLLM_MODEL=file-model\nDATABASE_URL=postgresql://x\n",
        encoding="utf-8",
    )

    settings = load_settings(env_file=env_file)

    assert settings.llm_model == "file-model"


# --- the key is a secret (FR-014, FR-016) ---


def test_the_key_never_appears_in_the_printed_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_environment(monkeypatch)
    settings = load_settings(env_file=None)

    for text in (repr(settings), str(settings), repr(settings.model_dump())):
        assert SENTINEL not in text


# --- configuration errors name the variable and never echo a value (FR-014, FR-017) ---


def test_a_missing_key_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "test-model")

    with pytest.raises(LLMConfigurationError, match="ANTHROPIC_API_KEY"):
        load_settings(env_file=None)


@pytest.mark.parametrize("model", [None, ""])
def test_a_missing_or_empty_model_names_the_variable(
    monkeypatch: pytest.MonkeyPatch, model: str | None
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    if model is not None:
        monkeypatch.setenv("LLM_MODEL", model)

    with pytest.raises(LLMConfigurationError, match="LLM_MODEL"):
        load_settings(env_file=None)


@pytest.mark.parametrize("timeout", ["0", "-7.25", "not-a-number-xyz"])
def test_an_invalid_timeout_names_the_variable_and_does_not_echo_the_value(
    monkeypatch: pytest.MonkeyPatch, timeout: str
) -> None:
    set_valid_environment(monkeypatch)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", timeout)

    with pytest.raises(LLMConfigurationError) as raised:
        load_settings(env_file=None)

    message = str(raised.value)
    assert "LLM_TIMEOUT_SECONDS" in message
    if timeout != "0":  # "0" also appears in the rule text "greater than 0"
        assert timeout not in message
    assert SENTINEL not in message


def test_a_configuration_error_has_no_cause_that_could_carry_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_valid_environment(monkeypatch)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "not-a-number-xyz")

    with pytest.raises(LLMConfigurationError) as raised:
        load_settings(env_file=None)

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


# --- nothing is read at import time (FR-017) ---


def test_importing_the_adapter_module_without_a_key_does_not_fail() -> None:
    environment = {k: v for k, v in os.environ.items() if k not in LLM_VARIABLES}
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")

    result = subprocess.run(
        [sys.executable, "-c", "import disputes.llm.anthropic_adapter"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
