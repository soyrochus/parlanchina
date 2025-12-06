import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAIError

from parlanchina.services.agent_backend import OpenAILLMBackend
from parlanchina.services.agent_engine import AgentEngine, AgentTurn
from parlanchina.services.agent_memory import InMemoryMemoryLayer
from parlanchina.services.agent_protocol import AgentLimits, AgentProfile, AgentState, HistoryEntry
from parlanchina.services.agent_tools import ToolRegistry, build_registry
from parlanchina.services.openai_client import get_async_client

logger = logging.getLogger(__name__)


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
    mode: str,
    internal_tools: Optional[List[str]] = None,
    mcp_tools: Optional[List[str]] = None,
) -> AsyncIterator[LLMEvent]:
    """Stream assistant text and image events with mode-aware tool selection."""

    internal_tools = internal_tools or []
    mcp_tools = mcp_tools or []

    if mode != "agent":
        # Ask mode: never pass tools to LLM, regardless of what's enabled in UI
        async for event in _stream_ask_mode(messages, model, enable_image_tool=False):
            yield event
        return

    async for event in _stream_agent_engine(
        messages,
        model,
        enabled_internal=list(internal_tools),
        enabled_mcp=list(mcp_tools),
    ):
        yield event


async def _stream_ask_mode(
    messages: List[dict],
    model: str,
    enable_image_tool: bool,
) -> AsyncIterator[LLMEvent]:
    """Single-shot ask mode using only internal tools (image generation)."""

    client = get_async_client()
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


async def _stream_agent_engine(
    messages: List[dict],
    model: str,
    enabled_internal: List[str],
    enabled_mcp: List[str],
) -> AsyncIterator[LLMEvent]:
    """Run the structured AgentEngine loop and emit UI-friendly events."""

    registry = build_registry(enabled_internal, enabled_mcp)
    profile = _build_agent_profile(registry)
    state = AgentState(
        goal=_latest_user_goal(messages),
        subgoals=[],
        mode="PLAN",
        step=0,
        history=_history_from_messages(messages),
        scratchpad="",
    )
    backend = OpenAILLMBackend(model=model)
    memory = InMemoryMemoryLayer()
    engine = AgentEngine(profile, registry, memory, backend)

    last_user = _latest_user_goal(messages)
    emitted_message = False
    async for turn in engine.run(state, last_user):
        for event in _emit_artifacts(turn):
            yield event
        if turn.message:
            emitted_message = True
            for chunk in _yield_text_chunks(turn.message):
                yield LLMEvent(type="text_delta", text=chunk)
            yield LLMEvent(type="text_done", text=turn.message)
        if turn.done:
            return

    if not emitted_message:
        yield LLMEvent(
            type="text_done",
            text="Agent loop completed without a final response.",
        )


def _emit_artifacts(turn: AgentTurn) -> List[LLMEvent]:
    events: list[LLMEvent] = []
    for artifact in turn.artifacts:
        if artifact.get("type") == "image":
            params = {
                "prompt": artifact.get("prompt"),
                "size": artifact.get("size"),
                "url_path": artifact.get("url_path"),
                "url": artifact.get("url"),
            }
            events.append(
                LLMEvent(
                    type="image_call",
                    image_b64=None,
                    image_params={k: v for k, v in params.items() if v},
                )
            )
    return events


def _latest_user_goal(messages: List[dict]) -> str:
    for message in reversed(messages or []):
        if message.get("role") == "user" and message.get("content"):
            return str(message.get("content"))
    return "Resolve the user request"


def _history_from_messages(messages: List[dict]) -> List[HistoryEntry]:
    history: list[HistoryEntry] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content") or message.get("raw_markdown") or ""
        if role in {"user", "assistant"}:
            history.append(HistoryEntry(role=role, content=content))
    return history


def _build_agent_profile(registry: ToolRegistry) -> AgentProfile:
    limits = AgentLimits(max_steps=6, max_tokens_per_call=4000, allow_destructive_tools=False)
    system_prompt = (
        "You are Parlanchina AgentEngine. Coordinate tools using the PLAN/ACT/REVIEW/DONE"
        " state machine. Keep responses short, factual, and stream-friendly."
    )
    tool_ids = [descriptor.id for descriptor in registry.describe()]
    return AgentProfile(
        id="default-agent",
        name="Parlanchina Agent",
        system_prompt=system_prompt,
        tool_ids=tool_ids,
        limits=limits,
        memory_packs=[],
    )


def _yield_text_chunks(text: str, chunk_size: int = 200) -> List[str]:
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


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

    client = get_async_client()
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
