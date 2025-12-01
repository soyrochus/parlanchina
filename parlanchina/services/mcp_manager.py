from __future__ import annotations

import asyncio
import importlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from flask import current_app

from parlanchina.paths import detect_mode, get_app_root

logger = logging.getLogger(__name__)

_fastmcp_spec = importlib.util.find_spec("fastmcp")
_fastmcp_available = _fastmcp_spec is not None

Client = None
SSETransport = None
StdioTransport = None

if _fastmcp_available:
    fastmcp_module = importlib.import_module("fastmcp")
    transport_module = importlib.import_module("fastmcp.client.transports")
    Client = fastmcp_module.Client
    SSETransport = transport_module.SSETransport
    StdioTransport = transport_module.StdioTransport


@dataclass
class MCPServerSummary:
    name: str
    transport_type: str
    description: str | None = None


@dataclass
class MCPToolSummary:
    name: str
    description: str
    input_schema: dict | None


@dataclass
class MCPToolResult:
    server_name: str
    tool_name: str
    raw_result: Any
    display_text: str


@dataclass
class _TransportConfig:
    type: str
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None


@dataclass
class _ServerConfig:
    name: str
    description: str | None
    transport: _TransportConfig


CONFIG_FILENAME = "mcp.json"

_config_error: str | None = None
_servers: dict[str, _ServerConfig] = {}
_config_path: Path | None = None
_config_mtime: float | None = None


def _determine_config_directory() -> Path:
    try:
        app = current_app._get_current_object()
        dirs = app.config.get("DIRS")
        if isinstance(dirs, dict) and dirs.get("config"):
            return Path(dirs["config"])
    except RuntimeError:
        # Outside of an application context; fall back to mode detection.
        pass

    mode = detect_mode()
    root = get_app_root(mode=mode)
    return root / "config"


def _resolve_config_path() -> Path:
    config_dir = _determine_config_directory()
    candidate = config_dir / CONFIG_FILENAME
    if candidate.exists():
        return candidate

    legacy = Path(__file__).resolve().parent.parent.parent / CONFIG_FILENAME
    if legacy.exists():
        return legacy
    return candidate


def _load_config_from_file(path: Path) -> tuple[dict[str, _ServerConfig], str | None]:
    if not path.exists():
        return {}, f"mcp.json not found at {path}"

    try:
        raw_config = json.loads(path.read_text())
    except json.JSONDecodeError:
        logger.exception("Failed to decode mcp.json at %s", path)
        return {}, "mcp.json is not valid JSON; MCP disabled"

    servers_blob = raw_config.get("servers")
    if isinstance(servers_blob, dict):
        normalized = []
        for name, server_cfg in servers_blob.items():
            if not isinstance(server_cfg, dict):
                continue
            entry: dict[str, Any] = {"name": name}
            if isinstance(server_cfg.get("description"), str):
                entry["description"] = server_cfg["description"]
            entry["transport"] = server_cfg.get("transport") or {
                "type": server_cfg.get("type", "stdio"),
                "command": server_cfg.get("command"),
                "args": server_cfg.get("args"),
                "env": server_cfg.get("env"),
                "url": server_cfg.get("url"),
                "headers": server_cfg.get("headers"),
            }
            normalized.append(entry)
        servers_blob = normalized
        logger.info("Loaded MCP config using map-style servers format from %s", path)
    if servers_blob is None and isinstance(raw_config.get("mcpServers"), dict):
        servers_blob = [
            {
                "name": name,
                "transport": {
                    "type": server_cfg.get("type", "stdio"),
                    "command": server_cfg.get("command"),
                    "args": server_cfg.get("args"),
                    "env": server_cfg.get("env"),
                    "url": server_cfg.get("url"),
                    "headers": server_cfg.get("headers"),
                },
            }
            for name, server_cfg in raw_config["mcpServers"].items()
            if isinstance(server_cfg, dict)
        ]
        logger.info("Loaded MCP config using legacy mcpServers format from %s", path)

    if not isinstance(servers_blob, list):
        return {}, "mcp.json missing 'servers' array; MCP disabled"

    parsed_servers: dict[str, _ServerConfig] = {}
    for entry in servers_blob:
        parsed = _parse_server(entry)
        if not parsed:
            continue
        parsed_servers[parsed.name] = parsed

    if not parsed_servers:
        return {}, "No valid MCP servers configured"
    return parsed_servers, None


def _ensure_servers_loaded() -> None:
    global _servers, _config_error, _config_path, _config_mtime

    path = _resolve_config_path()
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        mtime = None

    if _config_path == path and _config_mtime == mtime:
        return

    _config_path = path
    _config_mtime = mtime
    _servers, _config_error = _load_config_from_file(path)
    if _config_error:
        logger.warning("MCP configuration issue: %s", _config_error)


def _parse_server(entry: dict[str, Any]) -> Optional[_ServerConfig]:
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    transport = entry.get("transport")
    if transport is None and entry.get("type"):
        transport = {
            "type": entry.get("type"),
            "command": entry.get("command"),
            "args": entry.get("args"),
            "env": entry.get("env"),
            "url": entry.get("url"),
            "headers": entry.get("headers"),
        }
    description = entry.get("description") if isinstance(entry.get("description"), str) else None

    if not isinstance(name, str) or not isinstance(transport, dict):
        return None

    transport_type = transport.get("type")
    if transport_type not in {"stdio", "sse"}:
        return None

    if transport_type == "stdio":
        command = transport.get("command")
        if not isinstance(command, str):
            logger.warning("Skipping MCP server %s: stdio transport missing command", name)
            return None
        args = transport.get("args") if isinstance(transport.get("args"), list) else []
        env = transport.get("env") if isinstance(transport.get("env"), dict) else None
        transport_cfg = _TransportConfig(
            type="stdio",
            command=command,
            args=[str(arg) for arg in args],
            env={k: str(v) for k, v in env.items()} if env else None,
        )
    else:
        url = transport.get("url")
        if not isinstance(url, str):
            logger.warning("Skipping MCP server %s: sse transport missing url", name)
            return None
        headers = transport.get("headers") if isinstance(transport.get("headers"), dict) else None
        transport_cfg = _TransportConfig(
            type="sse",
            url=url,
            headers={k: str(v) for k, v in headers.items()} if headers else None,
        )

    return _ServerConfig(name=name, description=description, transport=transport_cfg)


def is_enabled() -> bool:
    _ensure_servers_loaded()
    return _fastmcp_available and bool(_servers)


def disabled_reason() -> str | None:
    _ensure_servers_loaded()
    if _fastmcp_available:
        return _config_error
    return "fastmcp is not installed"


def list_servers() -> list[MCPServerSummary]:
    _ensure_servers_loaded()
    return [
        MCPServerSummary(
            name=server.name,
            transport_type=server.transport.type,
            description=server.description,
        )
        for server in _servers.values()
    ]


def list_tools(server_name: str) -> list[MCPToolSummary]:
    _ensure_servers_loaded()
    server = _servers.get(server_name)
    if not server:
        raise ValueError(f"Unknown MCP server: {server_name}")
    if not is_enabled():
        return []
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_list_tools_async(server))
    else:
        raise RuntimeError("list_tools cannot be called from a running event loop; use list_tools_async")


async def list_tools_async(server_name: str) -> list[MCPToolSummary]:
    _ensure_servers_loaded()
    server = _servers.get(server_name)
    if not server:
        raise ValueError(f"Unknown MCP server: {server_name}")
    if not is_enabled():
        return []
    return await _list_tools_async(server)


def list_all_tools() -> list[dict[str, Any]]:
    """Return flattened tools across all servers with stable ids."""
    _ensure_servers_loaded()
    tools: list[dict[str, Any]] = []
    if not is_enabled():
        return tools
    for server_name in _servers:
        for tool in list_tools(server_name):
            tools.append(
                {
                    "server": server_name,
                    "name": tool.name,
                    "id": f"{server_name}.{tool.name}",
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
            )
    return tools


def get_tool_definition(tool_id: str) -> Optional[dict[str, Any]]:
    """Map a tool id like 'server.tool' to its full definition."""
    _ensure_servers_loaded()
    if "." not in tool_id:
        return None
    server_name, tool_name = tool_id.split(".", 1)
    try:
        tools = list_tools(server_name)
    except ValueError:
        return None

    for tool in tools:
        if tool.name == tool_name:
            return {
                "server": server_name,
                "name": tool.name,
                "id": tool_id,
                "full_name": f"{server_name}.{tool.name}",
                "description": tool.description,
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            }
    return None


async def get_tool_definition_async(tool_id: str) -> Optional[dict[str, Any]]:
    """Async variant for contexts that already run an event loop."""
    _ensure_servers_loaded()
    if "." not in tool_id:
        return None
    server_name, tool_name = tool_id.split(".", 1)
    try:
        tools = await list_tools_async(server_name)
    except ValueError:
        return None

    for tool in tools:
        if tool.name == tool_name:
            return {
                "server": server_name,
                "name": tool.name,
                "id": tool_id,
                "full_name": f"{server_name}.{tool.name}",
                "description": tool.description,
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            }
    return None


def call_tool(server_name: str, tool_name: str, args: dict[str, Any]) -> MCPToolResult:
    _ensure_servers_loaded()
    server = _servers.get(server_name)
    if not server:
        raise ValueError(f"Unknown MCP server: {server_name}")
    if not is_enabled():
        return MCPToolResult(
            server_name=server_name,
            tool_name=tool_name,
            raw_result=None,
            display_text="MCP is disabled because fastmcp is not installed or no servers are configured.",
        )
    try:
        return asyncio.run(_call_tool_async(server, tool_name, args or {}))
    except Exception as exc:  # pragma: no cover - defensive logging for unexpected errors
        logger.exception("Error calling MCP tool %s on %s", tool_name, server_name)
        return MCPToolResult(
            server_name=server_name,
            tool_name=tool_name,
            raw_result=None,
            display_text=f"Failed to run {tool_name} on {server_name}: {exc}",
        )


async def call_tool_async(server_name: str, tool_name: str, args: dict[str, Any]) -> MCPToolResult:
    _ensure_servers_loaded()
    server = _servers.get(server_name)
    if not server:
        raise ValueError(f"Unknown MCP server: {server_name}")
    if not is_enabled():
        return MCPToolResult(
            server_name=server_name,
            tool_name=tool_name,
            raw_result=None,
            display_text="MCP is disabled because fastmcp is not installed or no servers are configured.",
        )
    try:
        return await _call_tool_async(server, tool_name, args or {})
    except Exception as exc:  # pragma: no cover - defensive logging for unexpected errors
        logger.exception("Error calling MCP tool %s on %s", tool_name, server_name)
        return MCPToolResult(
            server_name=server_name,
            tool_name=tool_name,
            raw_result=None,
            display_text=f"Failed to run {tool_name} on {server_name}: {exc}",
        )


async def _list_tools_async(server: _ServerConfig) -> list[MCPToolSummary]:
    transport = _build_transport(server.transport)
    async with Client(transport=transport, name=f"parlanchina-{server.name}") as client:  # type: ignore[arg-type]
        tools = await client.list_tools()
        summaries: list[MCPToolSummary] = []
        for tool in tools:
            description = tool.description or tool.title or ""
            input_schema = _extract_schema(tool)
            summaries.append(
                MCPToolSummary(
                    name=tool.name,
                    description=description,
                    input_schema=input_schema,
                )
            )
        return summaries


async def _call_tool_async(server: _ServerConfig, tool_name: str, args: dict[str, Any]) -> MCPToolResult:
    transport = _build_transport(server.transport)
    async with Client(transport=transport, name=f"parlanchina-{server.name}") as client:  # type: ignore[arg-type]
        result = await client.call_tool(tool_name, arguments=args, raise_on_error=False)

    display = _format_result_text(server.name, tool_name, result)
    return MCPToolResult(
        server_name=server.name,
        tool_name=tool_name,
        raw_result=_serialize_call_result(result),
        display_text=display,
    )


def _build_transport(config: _TransportConfig):
    if config.type == "stdio" and StdioTransport:
        return StdioTransport(
            command=config.command or "",
            args=config.args or [],
            env=config.env,
        )
    if config.type == "sse" and SSETransport:
        return SSETransport(
            url=config.url or "",
            headers=config.headers,
        )
    raise ValueError(f"Unsupported transport: {config.type}")


def _extract_schema(tool: Any) -> dict | None:
    schema = getattr(tool, "input_schema", None)
    if not schema:
        schema = getattr(tool, "inputSchema", None)
    if isinstance(schema, dict):
        return schema
    try:
        if hasattr(schema, "model_dump"):
            dumped = schema.model_dump()
            return dumped if isinstance(dumped, dict) else None
    except Exception:
        return None
    return None


def _format_result_text(server_name: str, tool_name: str, result: Any) -> str:
    try:
        payload = result.result if hasattr(result, "result") else getattr(result, "raw", {})
    except Exception:
        payload = {}
    if not payload:
        payload = _serialize_call_result(result)
    serialized = _safe_json(payload)
    body = json.dumps(serialized, indent=2)
    return f"Result from {server_name}/{tool_name}:\n{body}"


def _safe_json(payload: Any) -> Any:
    try:
        json.dumps(payload)
        return payload
    except TypeError:
        return json.loads(json.dumps(payload, default=str))


def _serialize_call_result(result: Any) -> Any:
    """Best-effort serialization for CallToolResult variants."""
    for attr in ("model_dump", "dict", "to_dict"):
        if hasattr(result, attr):
            try:
                candidate = getattr(result, attr)()
                return _safe_json(candidate)
            except TypeError:
                try:
                    candidate = getattr(result, attr)(mode="json")
                    return _safe_json(candidate)
                except Exception:
                    continue
            except Exception:
                continue
    if hasattr(result, "__dict__"):
        try:
            return _safe_json(result.__dict__)
        except Exception:
            pass
    return _safe_json(result)
