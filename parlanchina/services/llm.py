import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import AsyncAzureOpenAI, AsyncOpenAI, OpenAIError

from parlanchina.services import image_store, internal_tools, mcp_manager

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
    mode: str,
    internal_tools: Optional[List[str]] = None,
    mcp_tools: Optional[List[str]] = None,
) -> AsyncIterator[LLMEvent]:
    """Stream assistant text and image events with mode-aware tool selection."""

    internal_tools = internal_tools or []
    mcp_tools = mcp_tools or []

    if mode != "agent":
        async for event in _stream_ask_mode(messages, model, enable_image_tool="internal.image" in set(internal_tools)):
            yield event
        return

    async for event in _stream_agent_mode(
        messages,
        model,
        enabled_internal=set(internal_tools),
        enabled_mcp=set(mcp_tools),
    ):
        yield event


async def _stream_ask_mode(
    messages: List[dict],
    model: str,
    enable_image_tool: bool,
) -> AsyncIterator[LLMEvent]:
    """Single-shot ask mode using only internal tools (image generation)."""

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


async def _stream_agent_mode(
    messages: List[dict],
    model: str,
    enabled_internal: set[str],
    enabled_mcp: set[str],
) -> AsyncIterator[LLMEvent]:
    """Handle iterative agent loop using both internal and MCP tools."""

    client = _get_client()
    tool_payloads, tool_name_map = await _build_agent_tool_payloads(
        enabled_internal_ids=enabled_internal, enabled_mcp_ids=enabled_mcp
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Agent loop start: internal=%s mcp=%s", sorted(enabled_internal), sorted(enabled_mcp))
        logger.debug("Agent tool payloads: %s", [p.get("function", {}).get("name") for p in tool_payloads])
    allowed_names = set(tool_name_map.keys())
    tool_results: list[str] = []
    last_structured: list[dict[str, Any]] = []
    conversation = _format_input(messages)

    # Plan step: ask the model for a brief plan before executing tools.
    try:
        available_tool_names = ", ".join(sorted(p.get("function", {}).get("name", "") for p in tool_payloads))
        plan_prompt = [
            {
                "role": "system",
                "content": (
                    "Given the user request, produce a brief, numbered plan of tool actions to complete it. "
                    "Keep it concise (1-3 steps). Available tools this turn: "
                    f"{available_tool_names or 'none'}. "
                    "Use only these tools for data/actions; do not invent other tools or browsing. "
                    "If no tools are needed, state that. Do not execute tools here."
                ),
            },
            {
                "role": "user",
                "content": messages[-1].get("content", "") if messages else "",
            },
        ]
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Plan prompt tools=%s user=%s", available_tool_names, plan_prompt[-1]["content"])
        plan_resp = await complete_response(plan_prompt, model)
        if plan_resp:
            conversation.insert(
                0,
                {
                    "role": "assistant",
                    "content": f"Plan:\n{plan_resp}",
                },
            )
            logger.debug("Plan response: %s", plan_resp)
    except Exception:
        # Planning is best-effort; continue if it fails.
        logger.debug("Plan step failed; continuing without plan", exc_info=True)
        pass
    if not tool_payloads:
        # No valid tools resolved; fall back to plain completion.
        logger.debug("No tool payloads; falling back to plain completion")
        final_text = await complete_response(messages, model)
        for chunk in _yield_text_chunks(final_text):
            yield LLMEvent(type="text_delta", text=chunk)
        yield LLMEvent(type="text_done", text=final_text)
        return

    if tool_payloads:
        tool_list = ", ".join(sorted(tool_name_map.keys()))
        conversation = [
            {
                "role": "system",
                "content": (
                    "You can call the available tools to fetch or modify data when it helps answer the user. "
                    f"Tools enabled for this turn: {tool_list}. "
                    "Call a tool when you need data or actions; otherwise answer directly. "
                    "When you return tool results, clearly surface the important fields in plain text (e.g., `Title: ...`, `Summary: ...`) before continuing. "
                    "If you both fetch data and generate media (like images), present the fetched fields first, then the media prompt/output. "
                    "Do not state that you lack web access; rely on the provided tools for data retrieval."
                ),
            }
        ] + conversation
    max_turns = 6
    for _ in range(max_turns):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=conversation,
                tools=tool_payloads,
                tool_choice="auto",
            )
        except OpenAIError as exc:
            logger.exception("Chat completion error: %s", exc)
            yield LLMEvent(type="error", text="Tool-enabled model call failed.")
            return
        except Exception as exc:  # pragma: no cover - catch-all safety
            logger.exception("Unexpected tool-call error: %s", exc)
            yield LLMEvent(type="error", text="Unexpected error during tool call.")
            return

        choice = (response.choices or [None])[0]
        message = getattr(choice, "message", None)
        if not message:
            break

        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            assistant_message = {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [_tool_call_to_dict(tc) for tc in tool_calls],
            }
            conversation.append(assistant_message)
            for tc in tool_calls:
                call = _tool_call_to_dict(tc)
                tool_name = call.get("function", {}).get("name") or ""
                args = _parse_tool_args(call.get("function", {}).get("arguments"))
                logger.debug("Tool call requested: %s args=%s", tool_name, args)
                # Accept both safe names and full ids from the model
                resolved_tool_id = tool_name_map.get(tool_name) or (
                    tool_name if tool_name in tool_name_map.values() else None
                )
                allowed = tool_name in allowed_names or tool_name in tool_name_map.values()
                if not resolved_tool_id or not allowed:
                    # Model asked for a tool that is not enabled this turn.
                    result_text = f"Tool {tool_name} is disabled for this turn."
                elif resolved_tool_id.startswith("internal."):
                    if resolved_tool_id not in enabled_internal:
                        result_text = f"Tool {tool_name} is disabled for this turn."
                    else:
                        result_text = await _run_internal_tool(resolved_tool_id, args)
                else:
                    if resolved_tool_id not in enabled_mcp:
                        result_text = f"Tool {tool_name} is disabled for this turn."
                    else:
                        result_text = await _run_mcp_tool(resolved_tool_id, args)
                logger.debug("Tool call result for %s: %s", tool_name, result_text[:500])
                tool_results.append(result_text)
                parsed_structured = _unwrap_tool_result(result_text)
                if parsed_structured:
                    last_structured.extend(parsed_structured)
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or "",
                        "content": result_text,
                        "name": tool_name or None,
                    }
                )
            continue

        final_text = message.content or ""
        if final_text:
            for chunk in _yield_text_chunks(final_text):
                yield LLMEvent(type="text_delta", text=chunk)
            yield LLMEvent(type="text_done", text=final_text)
            return

    # If we reach here, we didn't get a final answer. Ask the model to summarize tool results.
    if tool_results:
        # Prefer structured extracts; otherwise, prefer non-error results; fall back to all results.
        summary_sources: list[str] = []
        if last_structured:
            try:
                summary_sources.append(json.dumps(last_structured, indent=2))
            except Exception:
                pass
        if not summary_sources:
            non_error = [r for r in tool_results if "failed to run" not in r.lower() and "error" not in r.lower()]
            if non_error:
                summary_sources = non_error
        if not summary_sources:
            summary_sources = tool_results

        # Pull the last user request to provide context.
        last_user = next((m.get("content") for m in reversed(messages) if m.get("role") == "user"), "")
        logger.debug("Summarization fallback: last_user=%s sources_count=%s", last_user, len(summary_sources))

        # Try one final turn with tools to allow finishing (including media generation).
        final_conversation = [
            {
                "role": "system",
                "content": (
                    "Provide a final answer to the user's request using the tool results below. "
                    "Clearly list key fields (e.g., Title, Description) and, if applicable, generate requested media via the available tools. "
                    "Ignore failed or irrelevant tool attempts."
                ),
            },
            {
                "role": "user",
                "content": f"User request: {last_user}\n\nTool results:\n" + "\n\n".join(summary_sources),
            },
        ]

        for _ in range(2):
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=final_conversation,
                    tools=tool_payloads,
                    tool_choice="auto",
                )
            except Exception:
                break

            choice = (resp.choices or [None])[0]
            msg = getattr(choice, "message", None)
            if not msg:
                continue
            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [_tool_call_to_dict(tc) for tc in tool_calls],
                }
                final_conversation.append(assistant_msg)
                for tc in tool_calls:
                    call = _tool_call_to_dict(tc)
                    tool_name = call.get("function", {}).get("name") or ""
                    args = _parse_tool_args(call.get("function", {}).get("arguments"))
                    resolved_tool_id = tool_name_map.get(tool_name) or (
                        tool_name if tool_name in tool_name_map.values() else None
                    )
                    allowed = tool_name in allowed_names or tool_name in tool_name_map.values()
                    if not resolved_tool_id or not allowed:
                        result_text = f"Tool {tool_name} is disabled for this turn."
                    elif resolved_tool_id.startswith("internal."):
                        if resolved_tool_id not in enabled_internal:
                            result_text = f"Tool {tool_name} is disabled for this turn."
                        else:
                            result_text = await _run_internal_tool(resolved_tool_id, args)
                    else:
                        if resolved_tool_id not in enabled_mcp:
                            result_text = f"Tool {tool_name} is disabled for this turn."
                        else:
                            result_text = await _run_mcp_tool(resolved_tool_id, args)
                    tool_results.append(result_text)
                    final_conversation.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id") or "",
                            "content": result_text,
                            "name": tool_name or None,
                        }
                    )
                continue

            final_text = msg.content or ""
            if final_text:
                for chunk in _yield_text_chunks(final_text):
                    yield LLMEvent(type="text_delta", text=chunk)
                yield LLMEvent(type="text_done", text=final_text)
                return

        # If still nothing, fall back to a concise summary without tools.
        summary_prompt = [
            {
                "role": "system",
                "content": (
                    "Provide a final answer to the user's request using the tool results below. "
                    "Clearly list key fields (e.g., Title, Description) and, if applicable, the requested media prompt/output. "
                    "Ignore earlier failed or irrelevant tool attempts."
                ),
            },
            {
                "role": "user",
                "content": f"User request: {last_user}\n\nTool results:\n" + "\n\n".join(summary_sources),
            },
        ]
        summary_text = await complete_response(summary_prompt, model)
        yield LLMEvent(type="text_done", text=summary_text)
        return

    yield LLMEvent(
        type="text_done",
        text="Tool call loop ended without a final response. Please try again or adjust your request.",
    )


async def _build_agent_tool_payloads(
    enabled_internal_ids: set[str],
    enabled_mcp_ids: set[str],
) -> tuple[List[dict], dict[str, str]]:
    """Return tool payloads and a map of safe names -> full ids."""
    payloads: List[dict] = []
    name_map: dict[str, str] = {}
    used_names: set[str] = set()

    # Internal tools
    for tool_id in enabled_internal_ids:
        definition = internal_tools.get_internal_tool_definition(tool_id)
        if not definition:
            continue
        safe_name = _safe_tool_name(definition["id"], used_names)
        used_names.add(safe_name)
        name_map[safe_name] = definition["id"]
        name_map[definition["id"]] = definition["id"]
        payloads.append(
            {
                "type": "function",
                "function": {
                    "name": safe_name,
                    "description": definition.get("description") or "",
                    "parameters": definition.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )

    # MCP tools
    for tool_id in enabled_mcp_ids:
        definition = await mcp_manager.get_tool_definition_async(tool_id)
        if not definition:
            continue
        safe_name = _safe_tool_name(definition["full_name"], used_names)
        used_names.add(safe_name)
        name_map[safe_name] = definition["full_name"]
        name_map[definition["full_name"]] = definition["full_name"]
        payloads.append(
            {
                "type": "function",
                "function": {
                    "name": safe_name,
                    "description": definition.get("description") or "",
                    "parameters": definition.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )
    return payloads, name_map


def _tool_call_to_dict(tool_call: Any) -> dict:
    try:
        return tool_call.model_dump()
    except Exception:
        pass
    try:
        return tool_call.to_dict()
    except Exception:
        pass
    function = getattr(tool_call, "function", None)
    return {
        "id": getattr(tool_call, "id", ""),
        "type": getattr(tool_call, "type", "function"),
        "function": {
            "name": getattr(function, "name", None) if function else None,
            "arguments": getattr(function, "arguments", None) if function else None,
        },
    }


async def _run_mcp_tool(tool_name: str, args: dict | None) -> str:
    if "." not in tool_name:
        return f"Tool name {tool_name} is not in server.tool format."
    server, name = tool_name.split(".", 1)
    try:
        result = await mcp_manager.call_tool_async(server, name, args or {})
        return result.display_text
    except Exception as exc:  # pragma: no cover - safety for MCP failures
        logger.exception("MCP tool %s/%s failed", server, name)
        return f"Failed to run {tool_name}: {exc}"


async def _run_internal_tool(tool_id: str, args: dict | None) -> str:
    if tool_id == "internal.image":
        return await _run_internal_image_tool(args or {})
    return f"Unknown internal tool: {tool_id}"


async def _run_internal_image_tool(args: dict) -> str:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return "Image generation failed: prompt is required."
    size = args.get("size") or "1024x1024"
    client = _get_client()
    try:
        response = await client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
        )
        data = response.data[0] if getattr(response, "data", None) else None
        b64_content = getattr(data, "b64_json", None) if data else None
        url = getattr(data, "url", None) if data else None
        if b64_content:
            meta = image_store.save_image_from_base64(b64_content)
            return f"Generated image:\n\n![{prompt}]({meta.url_path})"
        if url:
            return f"Generated image:\n\n![{prompt}]({url})"
        return "Image generation failed: empty response."
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Internal image tool failed")
        return f"Image generation failed: {exc}"


def _parse_tool_args(raw_args: Any) -> dict:
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _unwrap_tool_result(raw: str) -> list[dict[str, Any]]:
    """Best-effort to extract structured rows from a tool result string."""
    if not raw or "text='" not in raw:
        return []
    # Extract the first text='...' segment
    try:
        start = raw.index("text='") + len("text='")
        end = raw.find("'", start)
        if end == -1:
            return []
        candidate = raw[start:end]
        # Unescape common sequences
        candidate = candidate.replace("\\n", "\n").replace("\\\"", '"').replace("\\'", "'")
        # If it looks like a JSON array or object, try to parse
        candidate_stripped = candidate.strip()
        if candidate_stripped.startswith("[") or candidate_stripped.startswith("{"):
            try:
                parsed = json.loads(candidate_stripped)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    return [parsed]
            except Exception:
                return []
    except Exception:
        return []
    return []


def _yield_text_chunks(text: str, chunk_size: int = 200) -> List[str]:
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _safe_tool_name(full_name: str, used: set[str]) -> str:
    """Generate an OpenAI-compliant tool name and keep a reverse map."""
    base = re.sub(r"[^a-zA-Z0-9_-]", "_", full_name) or "tool"
    candidate = base
    suffix = 1
    while candidate in used:
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate


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
