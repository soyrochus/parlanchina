import json
import logging
from typing import Any

from flask import Blueprint, abort, jsonify, request

from parlanchina.services import chat_store, mcp_manager

bp = Blueprint("mcp", __name__, url_prefix="/mcp")
logger = logging.getLogger(__name__)


def _safe_for_json(payload: Any) -> Any:
    try:
        json.dumps(payload)
        return payload
    except TypeError:
        return json.loads(json.dumps(payload, default=str))


@bp.get("/servers")
def get_servers():
    servers = [
        {
            "name": server.name,
            "transport": server.transport_type,
            "description": server.description,
        }
        for server in mcp_manager.list_servers()
    ]
    return jsonify(
        {
            "enabled": mcp_manager.is_enabled(),
            "reason": mcp_manager.disabled_reason(),
            "servers": servers,
        }
    )


@bp.get("/servers/<server_name>/tools")
def get_tools(server_name: str):
    if not mcp_manager.is_enabled():
        abort(503, mcp_manager.disabled_reason() or "MCP is disabled")

    try:
        tools = mcp_manager.list_tools(server_name)
    except ValueError:
        abort(404, f"Unknown MCP server: {server_name}")

    return jsonify(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ]
    )


@bp.post("/servers/<server_name>/tools/<tool_name>")
def run_tool(server_name: str, tool_name: str):
    payload = request.get_json(silent=True) or {}
    args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
    session_id = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None

    try:
        result = mcp_manager.call_tool(server_name, tool_name, args)
    except ValueError:
        abort(404, f"Unknown MCP server: {server_name}")

    message_html = None
    raw_markdown = result.display_text
    if session_id:
        session = chat_store.load_session(session_id)
        if session:
            message = chat_store.append_assistant_message(session_id, raw_markdown)
            message_html = message.get("html")

    return jsonify(
        {
            "result": {
                "server": result.server_name,
                "tool": result.tool_name,
                "raw": _safe_for_json(result.raw_result),
                "display": result.display_text,
            },
            "message_html": message_html,
            "raw_markdown": raw_markdown,
        }
    )


@bp.get("/tools")
def list_tools():
    """Return all known tools and their enabled state for a session."""
    if not mcp_manager.is_enabled():
        return jsonify(
            {
                "enabled": False,
                "reason": mcp_manager.disabled_reason(),
                "tools": [],
            }
        )

    session_id = request.args.get("session_id")
    if not session_id:
        abort(400, "session_id is required")

    session = chat_store.load_session(session_id)
    if not session:
        abort(404, "Session not found")

    tools = mcp_manager.list_all_tools()
    available_ids = {tool["id"] for tool in tools}

    enabled = chat_store.get_enabled_tools(session_id)
    if enabled is None:
        # Default to all available tools for this session
        enabled = sorted(available_ids)
        chat_store.set_enabled_tools(session_id, enabled)

    enabled_set = set(enabled)
    # Remove stale tool ids that no longer exist
    cleaned_enabled = sorted(enabled_set.intersection(available_ids))
    if cleaned_enabled != enabled:
        chat_store.set_enabled_tools(session_id, cleaned_enabled)
        enabled_set = set(cleaned_enabled)

    return jsonify(
        {
            "enabled": True,
            "tools": [
                {
                    "server": tool["server"],
                    "name": tool["name"],
                    "id": tool["id"],
                    "description": tool.get("description") or "",
                    "applied": tool["id"] in enabled_set,
                }
                for tool in tools
            ],
        }
    )


@bp.post("/tools/selection")
def update_tool_selection():
    """Persist enabled tool ids for a session."""
    if not mcp_manager.is_enabled():
        abort(503, mcp_manager.disabled_reason() or "MCP is disabled")

    payload = request.get_json(force=True)
    session_id = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None
    enabled_tools = payload.get("enabled_tools") if isinstance(payload.get("enabled_tools"), list) else None
    if not session_id:
        abort(400, "session_id is required")
    if enabled_tools is None:
        abort(400, "enabled_tools must be a list of tool ids")

    session = chat_store.load_session(session_id)
    if not session:
        abort(404, "Session not found")

    tools = mcp_manager.list_all_tools()
    valid_ids = {tool["id"] for tool in tools}
    normalized = [tool_id for tool_id in enabled_tools if isinstance(tool_id, str) and tool_id in valid_ids]

    chat_store.set_enabled_tools(session_id, normalized)
    return jsonify({"status": "ok", "enabled_tools": normalized})
