"""Tool registry and invokers for Agent Mode."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

from parlanchina.services import image_store, internal_tools, mcp_manager
from parlanchina.services.openai_client import get_async_client

from .agent_protocol import ToolDescriptor, ToolInvocation, ToolResult

logger = logging.getLogger(__name__)


ToolRunner = Callable[[ToolInvocation], Awaitable[ToolResult]]


@dataclass
class ToolRegistry:
    descriptors: List[ToolDescriptor]
    runners: Dict[str, ToolRunner] = field(default_factory=dict)

    def describe(self) -> List[ToolDescriptor]:
        return list(self.descriptors)

    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        runner = self.runners.get(invocation.tool_id)
        if not runner:
            return ToolResult(
                invocation_id=invocation.id,
                tool_id=invocation.tool_id,
                content=f"Tool {invocation.tool_id} is not available in this session.",
                success=False,
            )
        return await runner(invocation)


async def _run_internal_image(invocation: ToolInvocation) -> ToolResult:
    args = invocation.args or {}
    prompt = (args.get("prompt") or "").strip()
    size = args.get("size") or "1024x1024"
    if not prompt:
        return ToolResult(
            invocation_id=invocation.id,
            tool_id=invocation.tool_id,
            content="Image generation failed: prompt is required.",
            success=False,
        )

    client = get_async_client()
    try:
        response = await client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
        )
        data = response.data[0] if getattr(response, "data", None) else None
        b64_content = getattr(data, "b64_json", None) if data else None
        url = getattr(data, "url", None) if data else None
        artifacts: list[dict[str, Any]] = []
        if b64_content:
            meta = image_store.save_image_from_base64(b64_content)
            artifacts.append(
                {"type": "image", "url_path": meta.url_path, "prompt": prompt, "size": size}
            )
        if url:
            artifacts.append({"type": "image", "url": url, "prompt": prompt, "size": size})
        content = (
            "Image generated successfully with prompt: " + prompt
            if artifacts
            else "Image generation failed: empty response."
        )
        return ToolResult(
            invocation_id=invocation.id,
            tool_id=invocation.tool_id,
            content=content,
            artifacts=artifacts,
            success=bool(artifacts),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Internal image tool failed")
        return ToolResult(
            invocation_id=invocation.id,
            tool_id=invocation.tool_id,
            content=f"Image generation failed: {exc}",
            success=False,
        )


async def _run_mcp(invocation: ToolInvocation) -> ToolResult:
    try:
        result = await mcp_manager.call_tool_async(invocation.tool_id, invocation.args or {})
        artifact: dict[str, Any] = {"type": "text", "content": result}
        return ToolResult(
            invocation_id=invocation.id,
            tool_id=invocation.tool_id,
            content=result,
            artifacts=[artifact],
            success=True,
        )
    except Exception as exc:  # pragma: no cover - mcp failures are expected occasionally
        logger.exception("MCP tool %s failed", invocation.tool_id)
        return ToolResult(
            invocation_id=invocation.id,
            tool_id=invocation.tool_id,
            content=f"Tool execution failed: {exc}",
            success=False,
        )


async def _run_internal(invocation: ToolInvocation) -> ToolResult:
    if invocation.tool_id == "internal.image":
        return await _run_internal_image(invocation)
    return ToolResult(
        invocation_id=invocation.id,
        tool_id=invocation.tool_id,
        content=f"Unknown internal tool: {invocation.tool_id}",
        success=False,
    )


def _descriptor_from_internal(tool_id: str) -> ToolDescriptor | None:
    definition = internal_tools.get_internal_tool_definition(tool_id)
    if not definition:
        return None
    return ToolDescriptor(
        id=definition["id"],
        name=definition["name"],
        description=definition.get("description") or "",
        parameters=definition.get("parameters") or {"type": "object", "properties": {}},
        destructive=False,
    )


def _descriptor_from_mcp(tool_id: str) -> ToolDescriptor | None:
    try:
        definition = mcp_manager.get_tool_definition(tool_id)
        if not definition:
            return None
        return ToolDescriptor(
            id=definition["full_name"],
            name=definition.get("name") or definition.get("full_name") or tool_id,
            description=definition.get("description") or "",
            parameters=definition.get("parameters") or {"type": "object", "properties": {}},
            destructive=bool(definition.get("destructive")),
        )
    except Exception:
        logger.debug("Failed to load MCP tool descriptor for %s", tool_id, exc_info=True)
        return None


def build_registry(enabled_internal: List[str], enabled_mcp: List[str]) -> ToolRegistry:
    descriptors: list[ToolDescriptor] = []
    runners: dict[str, ToolRunner] = {}

    for tool_id in enabled_internal:
        descriptor = _descriptor_from_internal(tool_id)
        if not descriptor:
            continue
        descriptors.append(descriptor)
        runners[tool_id] = _run_internal

    for tool_id in enabled_mcp:
        descriptor = _descriptor_from_mcp(tool_id)
        if not descriptor:
            continue
        descriptors.append(descriptor)
        runners[tool_id] = _run_mcp

    return ToolRegistry(descriptors=descriptors, runners=runners)


def safe_args(raw_args: Any) -> dict:
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
