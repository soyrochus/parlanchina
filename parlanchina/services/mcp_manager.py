from __future__ import annotations

import asyncio
import importlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

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


_config_error: str | None = None
_servers: dict[str, _ServerConfig] = {}


def _load_config() -> dict[str, _ServerConfig]:
    global _config_error
    # Go up to project root: services -> parlanchina -> project root
    path = Path(__file__).resolve().parent.parent.parent / "mcp.json"
    if not path.exists():
        _config_error = "mcp.json not found; MCP disabled"
        return {}

    try:
        raw_config = json.loads(path.read_text())
    except json.JSONDecodeError:
        _config_error = "mcp.json is not valid JSON; MCP disabled"
        logger.exception("Failed to decode mcp.json")
        return {}

    servers_blob = raw_config.get("servers")
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
        logger.info("Loaded MCP config using legacy mcpServers format")

    if not isinstance(servers_blob, list):
        _config_error = "mcp.json missing 'servers' array; MCP disabled"
        return {}

    parsed_servers: dict[str, _ServerConfig] = {}
    for entry in servers_blob:
        parsed = _parse_server(entry)
        if not parsed:
            continue
        parsed_servers[parsed.name] = parsed

    if not parsed_servers:
        _config_error = "No valid MCP servers configured"
    return parsed_servers


def _parse_server(entry: dict[str, Any]) -> Optional[_ServerConfig]:
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    transport = entry.get("transport")
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


_servers = _load_config()


def is_enabled() -> bool:
    return _fastmcp_available and bool(_servers)


def disabled_reason() -> str | None:
    if _fastmcp_available:
        return _config_error
    return "fastmcp is not installed"


def list_servers() -> list[MCPServerSummary]:
    return [
        MCPServerSummary(
            name=server.name,
            transport_type=server.transport.type,
            description=server.description,
        )
        for server in _servers.values()
    ]


def list_tools(server_name: str) -> list[MCPToolSummary]:
    server = _servers.get(server_name)
    if not server:
        raise ValueError(f"Unknown MCP server: {server_name}")
    if not is_enabled():
        return []
    return asyncio.run(_list_tools_async(server))


def call_tool(server_name: str, tool_name: str, args: dict[str, Any]) -> MCPToolResult:
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
        raw_result=result.model_dump(mode="json"),
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
    serialized = _safe_json(payload)
    body = json.dumps(serialized, indent=2)
    return f"Result from {server_name}/{tool_name}:\n{body}"


def _safe_json(payload: Any) -> Any:
    try:
        json.dumps(payload)
        return payload
    except TypeError:
        return json.loads(json.dumps(payload, default=str))
