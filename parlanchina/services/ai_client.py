import asyncio
import logging
import os
import time
from typing import AsyncGenerator, List

from openai import AsyncAzureOpenAI, AsyncOpenAI
from openai import OpenAIError

logger = logging.getLogger(__name__)

_provider = os.getenv("OPENAI_PROVIDER", "openai").lower()
_api_key = os.getenv("OPENAI_API_KEY")
_api_base = os.getenv("OPENAI_API_BASE")
_api_version = os.getenv("OPENAI_API_VERSION")

_client = None


def _get_client():
    global _client
    if _client:
        return _client

    if _provider == "azure":
        _client = AsyncAzureOpenAI(
            api_key=_api_key,
            api_version=_api_version,
            azure_endpoint=_api_base,
        )
    else:
        _client = AsyncOpenAI(api_key=_api_key, base_url=_api_base)
    return _client


async def stream_chat_completion(
    messages: List[dict], model: str
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields streamed chunks of assistant text.
    """

    client = _get_client()
    started = time.time()
    total_chars = 0
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                total_chars += len(delta)
                yield delta
    except OpenAIError as exc:
        logger.exception("AI backend error: %s", exc)
        yield "\n\n*System:* An error occurred while contacting the model."
    except Exception as exc:  # pragma: no cover - catch-all safety
        logger.exception("Unexpected AI streaming error: %s", exc)
        yield "\n\n*System:* Unexpected error while streaming the response."
    finally:
        elapsed = time.time() - started
        logger.info(
            "Model %s streamed %s chars in %.2fs", model, total_chars, elapsed
        )


async def chat_completion(messages: List[dict], model: str) -> str:
    """
    Non-streaming chat completion that returns the full response.
    Used for generating session titles and other background tasks.
    """
    client = _get_client()
    started = time.time()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
        )
        content = response.choices[0].message.content or ""
        elapsed = time.time() - started
        logger.info(
            "Model %s completed %s chars in %.2fs", model, len(content), elapsed
        )
        return content
    except OpenAIError as exc:
        logger.exception("AI backend error: %s", exc)
        return "Error generating response"
    except Exception as exc:  # pragma: no cover - catch-all safety
        logger.exception("Unexpected AI error: %s", exc)
        return "Unexpected error"
