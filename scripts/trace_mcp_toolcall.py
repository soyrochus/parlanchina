"""
Utility script to observe raw OpenAI Responses tool-call events using MCP tools.

Usage:
  uv run python scripts/trace_mcp_toolcall.py "Describe a few tables" --model gpt-4o-mini

Requirements:
  - OPENAI_API_KEY set (and OPENAI_API_BASE/VERSION if needed)
  - MCP config in mcp.json; Postgres MCP server reachable
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any, Dict, List

from openai import AsyncAzureOpenAI, AsyncOpenAI
from pathlib import Path
from dotenv import load_dotenv
from parlanchina.services import mcp_manager

# Load .env from repository root (parent of scripts/)
_this_file = Path(__file__).resolve()
_dotenv_path = _this_file.parent.parent / ".env"
load_dotenv(dotenv_path=str(_dotenv_path))


def _get_client() -> Any:
    provider = os.getenv("OPENAI_PROVIDER", "openai").lower()
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    api_version = os.getenv("OPENAI_API_VERSION")

    if provider == "azure":
        return AsyncAzureOpenAI(api_key=api_key, api_version=api_version, azure_endpoint=api_base)
    return AsyncOpenAI(api_key=api_key, base_url=api_base)


def _build_tools() -> List[dict]:
    tools: List[dict] = []
    for server in mcp_manager.list_servers():
        try:
            tool_list = mcp_manager.list_tools(server.name)
        except Exception as exc:
            print(f"[WARN] Skipping server {server.name}: {exc}")
            continue
        for tool in tool_list:
            if not tool.input_schema:
                continue
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"{server.name}::{tool.name}",
                        "description": tool.description or "",
                        "parameters": tool.input_schema,
                    },
                }
            )
    return tools


async def main():
    parser = argparse.ArgumentParser(description="Trace OpenAI Responses tool-call events with MCP tools.")
    parser.add_argument("prompt", help="User prompt to send")
    parser.add_argument("--model", default=os.getenv("PARLANCHINA_DEFAULT_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()

    tools = _build_tools()
    if not tools:
        print("No MCP tools available. Ensure mcp.json and servers are reachable.")
        return

    client = _get_client()
    messages = [{"role": "user", "content": args.prompt}]
    print(f"Sending prompt to model={args.model} with {len(tools)} tool(s)...\n")

    stream = await client.responses.create(model=args.model, input=messages, tools=tools, stream=True)
    async for event in stream:
        payload = getattr(event, "model_dump", lambda: getattr(event, "__dict__", {}))()
        print(json.dumps({"type": getattr(event, 'type', None), "payload": payload}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
