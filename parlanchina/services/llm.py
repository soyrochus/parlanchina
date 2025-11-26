import logging
import os
import time
from collections.abc import AsyncGenerator
from typing import List

from openai import AsyncAzureOpenAI, AsyncOpenAI, OpenAIError

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


def _format_input(messages: List[dict]) -> List[dict]:
    formatted: List[dict] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content") or ""
        formatted.append({"role": role, "content": content})
    return formatted


async def stream_response(
    messages: List[dict], model: str
) -> AsyncGenerator[str, None]:
    """Stream assistant text chunks using the OpenAI Responses API."""

    client = _get_client()
    started = time.time()
    total_chars = 0
    formatted_messages = _format_input(messages)

    try:
        stream = await client.responses.create(
            model=model,
            input=formatted_messages,
            stream=True,
        )
        async for event in stream:
            if event.type == "response.output_text.delta":
                delta = event.delta or ""
                if delta:
                    total_chars += len(delta)
                    yield delta
    except OpenAIError as exc:
        logger.exception("Responses API error: %s", exc)
        yield "\n\n*System:* An error occurred while contacting the model."
    except Exception as exc:  # pragma: no cover - catch-all safety
        logger.exception("Unexpected LLM streaming error: %s", exc)
        yield "\n\n*System:* Unexpected error while streaming the response."
    finally:
        elapsed = time.time() - started
        logger.info(
            "Model %s streamed %s chars in %.2fs", model, total_chars, elapsed
        )


def _extract_text_output(response) -> str:
    if hasattr(response, "output_text"):
        text = getattr(response, "output_text") or ""
        if text:
            return text

    output = getattr(response, "output", None)
    if output:
        parts: list[str] = []
        for item in output:
            content = getattr(item, "content", []) or []
            for piece in content:
                text = getattr(piece, "text", None)
                if text:
                    parts.append(text)
        if parts:
            return "".join(parts)

    return ""


async def complete_response(messages: List[dict], model: str) -> str:
    """Return a full assistant response using the Responses API."""

    client = _get_client()
    started = time.time()
    formatted_messages = _format_input(messages)

    try:
        response = await client.responses.create(
            model=model,
            input=formatted_messages,
        )
        content = _extract_text_output(response)
        elapsed = time.time() - started
        logger.info(
            "Model %s completed %s chars in %.2fs", model, len(content), elapsed
        )
        return content or ""
    except OpenAIError as exc:
        logger.exception("Responses API error: %s", exc)
        return "Error generating response"
    except Exception as exc:  # pragma: no cover - catch-all safety
        logger.exception("Unexpected LLM error: %s", exc)
        return "Unexpected error"
