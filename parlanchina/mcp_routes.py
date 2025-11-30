import json
import logging
from typing import Any

from flask import Blueprint, abort, jsonify, request

from parlanchina.services import chat_store, internal_tools, mcp_manager

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
    session_id = request.args.get("session_id")
    if not session_id:
        abort(400, "session_id is required")

    return jsonify(_build_tool_payload(session_id))



@bp.post("/tools/selection")
def update_tool_selection():
    """Persist enabled tool ids for a session."""
    payload = request.get_json(force=True)
    session_id = payload.get("session_id") if isinstance(payload.get("session_id"), str) else None
    mode = payload.get("mode") if isinstance(payload.get("mode"), str) else None
    enabled_mcp_tools = payload.get("enabled_mcp_tools") if isinstance(payload.get("enabled_mcp_tools"), list) else None
    enabled_internal_tools = (
        payload.get("enabled_internal_tools") if isinstance(payload.get("enabled_internal_tools"), list) else None
    )
    if not session_id:
        abort(400, "session_id is required")

    session = chat_store.load_session(session_id)
    if not session:
        abort(404, "Session not found")

    current_mode = chat_store.get_mode(session_id)
    if mode in {"ask", "agent"}:
        chat_store.set_mode(session_id, mode)
        current_mode = mode

    # Internal tools
    internal_valid_ids = set(internal_tools.all_tool_ids())
    if enabled_internal_tools is not None:
        normalized_internal = [tool_id for tool_id in enabled_internal_tools if tool_id in internal_valid_ids]
        chat_store.set_enabled_internal_tools(session_id, normalized_internal)

    # MCP tools (only if MCP manager is up)
    if enabled_mcp_tools is not None and mcp_manager.is_enabled():
        mcp_defs = mcp_manager.list_all_tools()
        valid_ids = {tool["id"] for tool in mcp_defs}
        normalized_mcp = [tool_id for tool_id in enabled_mcp_tools if tool_id in valid_ids]
        chat_store.set_enabled_mcp_tools(session_id, normalized_mcp)

    # Respond with updated state
    return jsonify(_build_tool_payload(session_id))


def _build_tool_payload(session_id: str) -> dict:
    session = chat_store.load_session(session_id)
    if not session:
        abort(404, "Session not found")

    mode = chat_store.get_mode(session_id)

    # Internal tools
    internal_defs = internal_tools.list_internal_tools()
    internal_ids = {tool["id"] for tool in internal_defs}
    internal_enabled = chat_store.get_enabled_internal_tools(session_id)
    if internal_enabled is None:
        internal_enabled = sorted(internal_ids)
        chat_store.set_enabled_internal_tools(session_id, internal_enabled)
    internal_enabled_set = set(internal_enabled)

    # MCP tools
    mcp_enabled = mcp_manager.is_enabled()
    mcp_reason = mcp_manager.disabled_reason()
    mcp_defs = mcp_manager.list_all_tools() if mcp_enabled else []
    available_mcp_ids = {tool["id"] for tool in mcp_defs}

    enabled_mcp = chat_store.get_enabled_mcp_tools(session_id)
    if enabled_mcp is None and mcp_enabled:
        enabled_mcp = sorted(available_mcp_ids)
        chat_store.set_enabled_mcp_tools(session_id, enabled_mcp or [])
    elif enabled_mcp is None:
        enabled_mcp = []

    # Remove stale tool ids that no longer exist
    cleaned_enabled_mcp = sorted(set(enabled_mcp).intersection(available_mcp_ids))
    if cleaned_enabled_mcp != enabled_mcp:
        chat_store.set_enabled_mcp_tools(session_id, cleaned_enabled_mcp)
        enabled_mcp = cleaned_enabled_mcp

    return {
        "mode": mode,
        "internal": [
            {
                "id": tool["id"],
                "name": tool["name"],
                "description": tool.get("description") or "",
                "applied": tool["id"] in internal_enabled_set,
            }
            for tool in internal_defs
        ],
        "mcp_enabled": mcp_enabled,
        "reason": mcp_reason,
        "mcp": [
            {
                "server": tool["server"],
                "name": tool["name"],
                "id": tool["id"],
                "description": tool.get("description") or "",
                "applied": tool["id"] in set(enabled_mcp),
            }
            for tool in mcp_defs
        ],
    }
