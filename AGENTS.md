You are an expert Python engineer with deep knowledge of the Model Context Protocol (MCP) and the FastMCP client library.

Extend the existing Flask + Jinja2 app **Parlanchina** by adding an **MCP client layer** implemented with **FastMCP**. The goal is to let the app read an `mcp.json` configuration file, connect to one or more MCP servers, list their tools, and invoke them from the UI.

Do NOT change the core chat logic. Add MCP as an optional, well-encapsulated extension.

---

## 1. Libraries and protocol

- Use the official **FastMCP** Python client (`fastmcp.Client`) as the only MCP client abstraction. It supports multiple transports (Stdio, SSE, etc.) and can infer transports when given appropriate configuration. :contentReference[oaicite:0]{index=0}  
- Assume MCP itself uses JSON-RPC 2.0 over transports such as **stdio** and **HTTP/SSE**, which are the two we care about. :contentReference[oaicite:1]{index=1}  

---

## 2. Configuration: `mcp.json`

- Read an `mcp.json` file from the project root at app startup.
- The configuration format for this app must be:

  - Top-level object:  
    - `servers`: array of MCP server definitions.

  - Each server definition:  
    - `name`: unique server identifier (string, used in UI and internal lookups).  
    - `transport`: object with:  
      - `type`: `"stdio"` or `"sse"`.  
      - For `"stdio"`:  
        - `command`: string, executable or script to run.  
        - `args`: optional array of strings.  
        - `env`: optional object of environment variables.  
      - For `"sse"`:  
        - `url`: string with the SSE endpoint.  
        - `headers`: optional object for HTTP headers.  

- If `mcp.json` is missing or malformed, MCP support should be disabled gracefully and the rest of the app must keep working.

---

## 3. Python MCP manager module

Create a dedicated module, e.g. `parlanchina/services/mcp_manager.py`, which encapsulates all MCP-related logic and hides FastMCP details from the rest of the app.

It must expose a **synchronous façade** suitable for use from Flask routes, while internally using async FastMCP calls.

### 3.1 Public API (interfaces)

Define these interfaces (you can choose concrete Python representations, but keep the semantics):

- Server summary:

  - `MCPServerSummary`  
    - `name: str`  
    - `transport_type: str`  // "stdio" or "sse"  
    - `description: str | None`  // optional, may be empty  

- Tool summary:

  - `MCPToolSummary`  
    - `name: str`  
    - `description: str`  
    - `input_schema: dict | None`  // JSON Schema or similar, may be None  

- Tool result:

  - `MCPToolResult`  
    - `server_name: str`  
    - `tool_name: str`  
    - `raw_result: any`  // the JSON result returned by the MCP server  
    - `display_text: str`  // a human-readable string for the chat UI  

- Public functions of `mcp_manager`:

  - `is_enabled() -> bool`  
    - Returns True if `mcp.json` was loaded and at least one server is configured.

  - `list_servers() -> list[MCPServerSummary]`  
    - Returns a list of all configured servers.

  - `list_tools(server_name: str) -> list[MCPToolSummary]`  
    - Connects to the given server (via FastMCP Client) and returns tool metadata.

  - `call_tool(server_name: str, tool_name: str, args: dict) -> MCPToolResult`  
    - Invokes the given tool with JSON-serializable arguments and returns the result.  
    - Must handle errors and timeouts and convert them into a safe `display_text`.

You may add internal helper classes/types as needed, but keep the external API simple and stable.

---

## 4. FastMCP integration details

- For each MCP call (`list_tools` or `call_tool`), create and use a FastMCP `Client` configured with the right transport:

  - For `"stdio"` servers, launch the configured `command` with `args` and `env`, using FastMCP’s stdio transport support. Stdio is the default for local MCP servers. :contentReference[oaicite:2]{index=2}  
  - For `"sse"` servers, use FastMCP’s SSE transport support to connect to the configured `url`. :contentReference[oaicite:3]{index=3}  

- Use FastMCP’s **async Client API** internally. The public `mcp_manager` methods should remain synchronous from the perspective of Flask routes.

  - You may choose one of these strategies (you implement one, not both):
    - Use a dedicated background asyncio event loop thread and `run_coroutine_threadsafe` to execute Client calls.  
    - Or, for simplicity, wrap each FastMCP call in `asyncio.run(...)`.  

  - In both cases, keep the implementation clear and easy to change later.

- Make sure that any resources (subprocesses, connections) are properly cleaned up after each call.

---

## 5. Error handling and robustness

- If a server cannot be started or connected, its tools should not break the whole app:
  - `list_servers()` should still return other servers.
  - `list_tools()` for a failing server should propagate a controlled error (e.g. empty list and/or logged error).
  - `call_tool()` should return an `MCPToolResult` with a `display_text` explaining the error in simple language, and log the technical details.

- MCP must be strictly **optional**:
  - If FastMCP is not installed, or `mcp.json` is missing, the rest of Parlanchina must still work.
  - In that case, `is_enabled()` must return False and calls to MCP-related endpoints should degrade gracefully.

---

## 6. Integration points in Parlanchina (only contracts, not UI code)

- Add a **new Flask blueprint or route group** to expose MCP functionality to the frontend, e.g.:

  - A route to list servers and tools for the UI (e.g. JSON responses).  
  - A route to invoke a tool and return the result (also JSON).

- Do NOT implement any agentic logic in this iteration:
  - For now, MCP tools are invoked explicitly by the user via the UI.
  - The LLM is not automatically deciding when to call tools; MCP is “manual use” only.

---

## 7. Quality expectations

- Keep the implementation small, readable, and well-commented.
- Clearly separate:
  - config parsing (`mcp.json`),
  - FastMCP client handling (transports, async),
  - and the sync façade (`mcp_manager` public API).
- Document in comments where we would later:
  - add automatic tool discovery into the LLM prompt,
  - support streaming tool results,
  - or support other transports.

Generate all necessary code and wiring so that a developer can:

1. Install FastMCP with uv add.  
2. Use the `mcp.json` file in the root of the project  
3. Start Parlanchina.  
4. From the UI, see MCP servers and tools and run a tool, receiving its result as part of the chat context.

