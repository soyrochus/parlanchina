import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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


@dataclass
class LLMEvent:
    type: str
    text: Optional[str] = None
    image_b64: Optional[str] = None
    image_params: Optional[Dict[str, Any]] = None
    raw_event: Any | None = None


def _event_to_dict(event: Any) -> dict:
    try:
        return event.model_dump()
    except Exception:
        try:
            return event.to_dict()
        except Exception:
            return getattr(event, "__dict__", {}) or {}


def _extract_image_b64(payload: dict) -> tuple[Optional[str], dict]:
    image_params: dict = {}

    def _maybe_extract_image_obj(node: dict) -> Optional[str]:
        # Common shapes: {"data": "...", "format": "png"} or {"image": {"data": "..."}}
        if "data" in node and isinstance(node["data"], str) and node["data"].strip():
            return node["data"]
        if "image" in node and isinstance(node["image"], dict):
            inner = node["image"]
            if "data" in inner and isinstance(inner["data"], str) and inner["data"].strip():
                return inner["data"]
            if "base64" in inner and isinstance(inner["base64"], str) and inner["base64"].strip():
                return inner["base64"]
        if "partial_image_b64" in node and isinstance(node["partial_image_b64"], str):
            return node["partial_image_b64"]
        return None

    def _walk(node: Any) -> Optional[str]:
        if isinstance(node, dict):
            for key in ("image_base64", "b64_json", "base64", "image", "partial_image_b64"):
                if key in node and isinstance(node[key], str) and node[key].strip():
                    return node[key]
            possible = _maybe_extract_image_obj(node)
            if possible:
                return possible
            for key in ("alt_text", "prompt", "description"):
                if key in node and key not in image_params:
                    image_params[key] = node[key]
            for value in node.values():
                found = _walk(value)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = _walk(item)
                if found:
                    return found
        return None

    return _walk(payload), image_params


async def stream_response(
    messages: List[dict],
    model: str,
    enable_image_tool: bool = True,
) -> AsyncIterator[LLMEvent]:
    """Stream assistant text and image events using the OpenAI Responses API."""

    client = _get_client()
    started = time.time()
    total_chars = 0
    formatted_messages = _format_input(messages)

    tools = None
    if enable_image_tool:
        tools = [
            {
                "type": "image_generation",
                "model": "gpt-image-1",
                "size": "1024x1024",
                "quality": "high",
                "output_format": "png",
            }
        ]

    try:
        stream = await client.responses.create(
            model=model,
            input=formatted_messages,
            stream=True,
            tools=tools,
        )
        accumulated_text = ""
        sent_image_start = False
        async for event in stream:
            payload = _event_to_dict(event)
            if logger.isEnabledFor(logging.DEBUG):
                event_type = getattr(event, "type", type(event))
                logger.debug(
                    "LLM stream event: %s keys=%s", event_type, list(payload.keys())
                )
                if "partial_image_b64" in payload:
                    logger.debug(
                        "Partial image payload size=%s",
                        len(payload.get("partial_image_b64") or ""),
                    )

            # Signal image generation start even before final base64 arrives
            if (
                not sent_image_start
                and isinstance(getattr(event, "type", ""), str)
                and "image_generation_call" in event.type
            ):
                sent_image_start = True
                yield LLMEvent(type="image_start", raw_event=event)

            # Look for image data on any event, even if the type label is unexpected
            image_b64, image_params = _extract_image_b64(payload)
            if image_b64:
                logger.debug("Image payload detected on event type %s", getattr(event, "type", ""))
                yield LLMEvent(
                    type="image_call",
                    image_b64=image_b64,
                    image_params=image_params,
                    raw_event=event,
                )
                continue

            if event.type == "response.output_text.delta":
                delta = event.delta or ""
                if delta:
                    accumulated_text += delta
                    total_chars += len(delta)
                    yield LLMEvent(
                        type="text_delta",
                        text=delta,
                        raw_event=event,
                    )
            elif event.type in {
                "response.output_text.done",
                "response.completed",
            }:
                text_content = _extract_text_output(event) or accumulated_text
                yield LLMEvent(
                    type="text_done",
                    text=text_content,
                    raw_event=event,
                )
            elif event.type == "response.error":
                yield LLMEvent(type="error", text=str(event), raw_event=event)
    except OpenAIError as exc:
        logger.exception("Responses API error: %s", exc)
        yield LLMEvent(
            type="error",
            text="\n\n*System:* An error occurred while contacting the model.",
        )
    except Exception as exc:  # pragma: no cover - catch-all safety
        logger.exception("Unexpected LLM streaming error: %s", exc)
        yield LLMEvent(
            type="error",
            text="\n\n*System:* Unexpected error while streaming the response.",
        )
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
