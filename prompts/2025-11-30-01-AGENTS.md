This is a followq-up of [the previous instruction prompt which you did not properly implemement](prompts/2025-11-29-02-AGENTS.md). Do NOT try to implement the instructions of that file, only use it for context.

Instead, use the instructins of [THIS file](./AGENTS.md) in oder to address the issiues 
You are an AI code-generation assistant working on an existing project called **Parlanchina**.

Parlanchina is a small local **Python + Flask** web app that:
- Provides a ChatGPT-style chat UI.
- Reads an `mcp.json` file, starts MCP servers, and already connects to them correctly.
- Can list tools from those MCP servers via an internal MCP manager service.
- Currently exposes a manual “MCP TOOL” selector with an “ARGS (JSON, OPTIONAL)” field and a “Run tool” button, which lets the user call one tool manually.

Your task: **do NOT touch the mcp.json handling or the MCP startup logic**. Those are correct. Instead, you must:
1. Replace the current manual MCP UI with a **single tools configuration widget**.
2. Wire the selected tools automatically into the LLM calls so the model can decide which tools to invoke.

---

## Desired behaviour

### MCP bootstrap (unchanged)

- Keep the current behaviour where:
  - `mcp.json` is read.
  - MCP servers are started / connected (via the existing `mcp_manager` or equivalent).
  - For each server, the available tools and their schemas can be queried.

**Do not re-implement or significantly change this.** Reuse the existing manager/service.

---

### New tools configuration UI

Replace the current “MCP TOOL / ARGS / Run tool” strip in the main chat view with a single configuration widget similar in spirit to GitHub Copilot’s “Configure Tools” dialog (see screenshot reference).

Requirements:

1. **Single tools panel** in the chat UI
   - Located **above the message input** and below the chat history.
   - No second selector above the input; no duplicated dropdowns.

2. **Hierarchical list with checkboxes**
   - Group tools by server.
   - For each server:
     - Show a collapsible row with a server label (e.g. `drivew`, `postgres-mcp`, etc.).
     - Under each server, list its tools; each tool has:
       - A checkbox (checked = enabled, unchecked = disabled).
       - A human-readable label such as `connect_db (postgres)` or `server_name:tool_name`.
   - Optionally provide:
     - A “Select all / Deselect all” for a server.
     - A global “Select all / Deselect all” at the top.

3. **State and persistence**
   - The enabled/disabled state should be **per chat session**.
   - When a session is opened or reloaded:
     - Load the current selection state from the backend (or from the session).
     - Reflect it in the checkboxes.
   - Default: when tools are first discovered for a new session, consider enabling all of them.

4. **No manual ‘Run tool’ in the chat**
   - Remove from the main chat view:
     - The manual “MCP TOOL” dropdown.
     - The “ARGS (JSON, OPTIONAL)” textbox.
     - The “Run tool” button.
   - If a separate “debug / playground” page is needed for manual calls, keep that **in another route**, not in the normal user chat.

Implementation guidelines:

- Add a small REST endpoint (or reuse an existing one) like `GET /mcp/tools` that returns:
  ```json
  [
    {
      "server": "drivew",
      "name": "connect_db",
      "id": "drivew.connect_db",      // unique identifier
      "description": "…",
      "enabled": true
    },
    ...
  ]
````

* Add another endpoint like `POST /mcp/tools/selection` or integrate selection updates into the chat endpoint to save the enabled set in the session.

---

### Automatic tool integration into LLM calls

When the user sends a message, the LLM must see the **enabled tools** as part of the tools list in the request. The model then decides whether to call them.

1. **Collect selected tools**

   * On “Send message”:

     * The frontend collects the IDs of all **checked** tools (e.g. `["drivew.connect_db", "other.server.tool"]`).
     * Send them with the chat request, e.g.:

       ```json
       {
         "message": "user text",
         "session_id": "...",
         "enabled_tools": ["drivew.connect_db", "other.server.tool"]
       }
       ```

2. **Build the tools list for the model**

   * In the Flask view / handler that sends requests to the LLM:

     * Use the existing MCP manager to map these IDs to their full tool definitions (name, description, parameters).

     * Build the `tools` (or `functions`) list in the format expected by the underlying LLM API (e.g. OpenAI tools).

       Pseudocode:

       ```python
       tools_for_llm = []
       for tool_id in enabled_tools:
           tool = mcp_manager.get_tool_definition(tool_id)  # you implement this helper
           tools_for_llm.append({
               "type": "function",
               "function": {
                   "name": tool["full_name"],          # e.g. "drivew.connect_db"
                   "description": tool["description"],
                   "parameters": tool["parameters"],   # JSON schema
               },
           })
       ```

     * If `tools_for_llm` is non-empty, pass it to the LLM call.

     * If empty, call the LLM without tools (pure chat).

3. **Tool call execution loop**

   * Reuse or implement the standard tool-calling loop:

     * Send user + system messages and `tools_for_llm` to the model.
     * If the response includes a tool call:

       * Parse the tool name (e.g. `drivew.connect_db`) and arguments.
       * Use the MCP manager to:

         * Find the correct MCP server.
         * Execute the tool with the provided args.
       * Add a `tool` message with the result back into the conversation.
       * Call the model again to get the final answer.
   * IMPORTANT: only allow the model to call tools that were actually enabled in this turn.

     * If a tool call is requested for a disabled tool, either:

       * Ignore and ask the model to respond without it, or
       * Return an error system message indicating the tool is disabled.

4. **No “active tool” concept**

   * Remove any logic that assumes “a single active / currently selected tool”.
   * Tools are simply **available or not** each turn, defined by the checkbox selection.

---

### Integration details & constraints

* Keep the project structure and style:

  * Use the existing Flask app, template engine, and front-end stack (plain JS / HTMX / Alpine / etc.).
  * Add minimal JS needed to:

    * Fetch tools list from the backend.
    * Render / update the checkbox list.
    * Include `enabled_tools` in the chat POST payload.
* Use the existing MCP manager module (e.g. `parlanchina.services.mcp_manager`) to:

  * Discover servers and tools.
  * Execute tool calls.
  * Get JSON schema for parameters.
* Add concise comments where behaviour might not be obvious:

  * How tools are filtered by `enabled_tools`.
  * How the mapping from `tool_id` to MCP server + tool works.

---

### What you must deliver

1. Backend changes:

   * Endpoints to:

     * List tools + enabled state per session.
     * Accept `enabled_tools` in chat requests and build the correct tools list for the LLM.
   * Integration with the existing MCP manager for discovery and invocation.
   * Updated chat handler implementing automatic tool-calling.

2. Frontend changes:

   * Removal of the manual “MCP TOOL / ARGS / Run tool” UI from the main chat.
   * A single tools configuration panel with hierarchical checkboxes (servers → tools).
   * Wiring so that sending a message includes the currently enabled tools.

3. Any necessary tests or small refactors to keep the code clean and maintainable.

Inspect the existing Parlanchina repository, identify the relevant files (Flask routes, templates, JS, MCP manager), and implement all of the above so that the UI behaves like a tools selector and the LLM automatically sees and calls the enabled MCP tools.

