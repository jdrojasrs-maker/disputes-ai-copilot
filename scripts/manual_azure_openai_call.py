"""One real call to an Azure OpenAI deployment, run by hand. NOT part of the tests and never run
in CI.

Usage (needs AZURE_OPENAI_BASE_URL, AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT in the
environment or in a local .env file):

    uv run python scripts/manual_azure_openai_call.py

It sends one short synthetic prompt and prints the answer text, the token usage, the model that
answered (the versioned name the service reports, which differs from the deployment name) and the
stop reason. It never prints the API key. A real call costs a small amount on your own resource.
"""

import asyncio
import os
import sys

from disputes.llm.azure_openai_adapter import AzureOpenAILLMClient
from disputes.llm.errors import LLMConfigurationError, LLMError
from disputes.llm.models import LLMRequest, Message, Role

SYSTEM_PROMPT = "You help a card-disputes team. Answer in one short sentence."
QUESTION = "In one sentence, what is a chargeback?"
MAX_TOKENS = 1024


async def main() -> int:
    if os.environ.get("CI"):
        print("Refusing to run: the CI environment variable is set. This script is manual only.")
        return 2

    try:
        client = AzureOpenAILLMClient.from_env()
    except LLMConfigurationError as error:
        print(f"Configuration error: {error}")
        return 2

    request = LLMRequest(
        system=SYSTEM_PROMPT,
        messages=[Message(role=Role.USER, content=QUESTION)],
        max_tokens=MAX_TOKENS,
    )
    print(f"Client:      {client!r}")
    print(f"System:      {request.system}")
    print(f"Question:    {QUESTION}")
    print(f"max_tokens:  {request.max_tokens} (sent as max_completion_tokens)")

    try:
        response = await client.complete(request)
    except LLMError as error:
        print(f"Call failed:  {type(error).__name__}: {error}")
        print(f"retryable:    {error.retryable}")
        print(f"status_code:  {error.status_code}")
        print(f"request_id:   {error.request_id}")
        return 1

    print(f"Answer:      {response.text}")
    print(f"Input tokens:  {response.usage.input_tokens}")
    print(f"Output tokens: {response.usage.output_tokens}")
    print(f"Model:       {response.model}")
    print(f"Stop reason: {response.stop_reason.value}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
