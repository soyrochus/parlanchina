**Unified Specification for Ask Mode and Agent Mode**

## 1. Overview

The system supports two fundamentally different execution models:

1. **Ask Mode** — a single, stateless model turn where the model may use **internal tools only** (e.g., image generation). MCP tools must be ignored.
2. **Agent Mode** — a multi-step orchestration loop where the model may use **both internal tools and MCP tools**, depending on the user-selected toolbox. The agent continues iterating until finish conditions are met.

The distinction must remain strict and predictable. Tools must never be mixed across modes unless explicitly configured.

---

## 2. Tool Types

### 2.1 Internal Tools

Internal tools are native to the application. They are always available and require no MCP server.
Examples:

* `image_gen` (local or OpenAI image generation). The current implementation!


They must be:

* Registered in a dedicated **internal tool registry**.
* Exposed in the UI tool selector.
* Enable/disable configurable per session.

### 2.2 MCP Tools

MCP tools are provided by external MCP servers launched at startup.
Examples:

* Postgres MCP server


For each active MCP server:

* Tools appear in the tool selector under the server’s namespace.
* Tools are only available in **Agent Mode**.
* If disabled in the selector, they must be omitted from the model’s tool schema.

---

## 3. Modes of Execution

---

## 3.1 Ask Mode (Single-Shot Query)

### Purpose

Direct question to the model; no iterative reasoning; no agent loop.

### Rules

* **Only internal tools are visible to the model**.
* **All MCP tools must be excluded** from the tool schema.
* Model produces **one response** containing either:

  * A direct natural-language answer, or
  * A single internal-tool call (e.g., image generation).

### UI Behavior

* Tool selector shows internal tools.
* MCP tools appear disabled or hidden.

### Server Behavior

* One call to the model.
* If model emits internal tool calls, they are executed.
* No second model turn after tool execution unless explicitly configured ("single tool call" pattern).

---

## 3.2 Agent Mode (Multi-Step Tool Orchestration)

### Purpose

Tasks requiring reasoning over multiple steps, e.g., DB query → transform → image generation → final answer.

### Behavior

* Agent loop executes:

  ```
  model → tool calls → results → model → … until final or limit
  ```
* All **enabled** tools are passed to the model:

  * Internal tools.
  * MCP tools (if active and selected).
* No special-casing; the model decides which tools to use.

### Stop Conditions

* Model returns a message with no tool calls and marked as final.
* Max number of steps reached.
* User cancels.

### Server Responsibilities

* Maintain iteration loop.
* Stream intermediate events to the client:

  * Tool call invoked
  * Tool result received
  * New model turn
* Enforce limits and guardrails.

---

## 4. Tool Availability Logic

### 4.1 Internal Tools

* Always registered.
* Enabled by default in Ask Mode.
* Enabled or disabled per session in Agent Mode depending on the user-selected toolbox.

### 4.2 MCP Tools

* Never available in Ask Mode.
* Available only in Agent Mode.
* Tool schemas must reflect the user’s selection:

  * If a tool/server is disabled in the selector, omit its schema entirely.

---

## 5. UI Requirements

### 5.1 Tool Selector

* Two sections:

  * **Internal Tools**
  * **MCP Tools** (grouped by server)
* Each tool has a toggle.
* Toggling changes the tool schema for subsequent model turns.

### 5.2 Mode Switch

* Explicit mode selector:

  * **Ask Mode**
  * **Agent Mode**
* Switching mode resets the current tool schema according to rules defined above.

### 5.3 Display During Agent Mode

* Show real-time stream of events:

  * Tool calls
  * Results
  * Intermediate model replies

---

## 6. Agent Loop Specification

Pseudo-algorithm:

```
if mode == ASK:
    available_tools = INTERNAL_TOOLS(enabled_only)
    call_model_once(available_tools)
    handle_optional_single_tool_call()
    return

if mode == AGENT:
    available_tools = INTERNAL_TOOLS(enabled_only) + MCP_TOOLS(enabled_only)

    messages = initial_user_message

    for step in range(MAX_STEPS):
        model_reply = call_model(messages, available_tools)

        if model_reply contains no tool calls:
            return final(model_reply)

        for tool_call in model_reply.tool_calls:
            result = execute(tool_call)
            messages.append(result_event)

        messages.append(model_reply)
```

---

## 7. Safety and Guardrails

* Step limit (e.g., 10).
* Token budget per full run.
* User cancel support.
* Log traces for debugging:

  * Model prompts
  * Tool schemas
  * Tool calls
  * Results

---

## 8. Expected Developer Tasks

* Implement two independent registries:
  `internal_tools` and `mcp_tools`.
* Mode-dependent assembly of the final tool schema.
* Proper UI grouping and toggling.
* Clean agent loop implementation.
* Streaming of intermediate events.
* Clear error handling when multiple tools are used.

