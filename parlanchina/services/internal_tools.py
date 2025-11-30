"""Registry for internal (non-MCP) tools.

Currently exposes a single image generation tool. Internal tools are available
without MCP servers and can be toggled per session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class InternalTool:
    id: str
    name: str
    description: str
    parameters: Dict[str, Any]


_TOOLS: List[InternalTool] = [
    InternalTool(
        id="internal.image",
        name="generate_image",
        description="Generate an image from a prompt.",
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Concise description of the desired image.",
                },
                "size": {
                    "type": "string",
                    "description": "Image size, e.g. 512x512, 1024x1024.",
                    "enum": ["512x512", "768x768", "1024x1024"],
                },
            },
            "required": ["prompt"],
        },
    ),
]


def list_internal_tools() -> List[dict]:
    """Return internal tools for UI consumption."""
    return [
        {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description,
        }
        for tool in _TOOLS
    ]


def get_internal_tool(tool_id: str) -> Optional[InternalTool]:
    for tool in _TOOLS:
        if tool.id == tool_id:
            return tool
    return None


def get_internal_tool_definition(tool_id: str) -> Optional[dict]:
    tool = get_internal_tool(tool_id)
    if not tool:
        return None
    return {
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
    }


def all_tool_ids() -> List[str]:
    return [tool.id for tool in _TOOLS]
