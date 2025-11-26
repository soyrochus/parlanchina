document.addEventListener("DOMContentLoaded", () => {
  const panel = document.getElementById("mcp-panel");
  if (!panel) return;

  const sessionId = panel.dataset.sessionId;
  const statusEl = document.getElementById("mcp-status");
  const controlsEl = document.getElementById("mcp-controls");
  const serverSelect = document.getElementById("mcp-server-select");
  const toolSelect = document.getElementById("mcp-tool-select");
  const argsInput = document.getElementById("mcp-args");
  const descriptionEl = document.getElementById("mcp-tool-description");
  const schemaEl = document.getElementById("mcp-tool-schema");
  const runButton = document.getElementById("mcp-run");
  const resultEl = document.getElementById("mcp-result");
  const messagesEl = document.getElementById("messages");
  const md = window.markdownit({ linkify: true, breaks: true });

  const renderMarkdown = (text) => DOMPurify.sanitize(md.render(text || ""));

  const updateStatus = (message, isError = false) => {
    statusEl.textContent = message;
    statusEl.classList.toggle("text-red-500", isError);
    statusEl.classList.toggle("dark:text-red-400", isError);
  };

  const appendAssistantBubble = (html) => {
    if (!messagesEl) return;
    const wrapper = document.createElement("div");
    wrapper.className = "flex justify-start";
    const bubble = document.createElement("div");
    bubble.className = "prose prose-slate dark:prose-invert max-w-3xl rounded-2xl bg-white/80 dark:bg-slate-800/70 px-4 py-3 shadow-sm";
    bubble.innerHTML = html;
    wrapper.appendChild(bubble);
    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  const loadServers = async () => {
    try {
      const response = await fetch("/mcp/servers");
      if (!response.ok) throw new Error("Failed to load servers");
      const data = await response.json();
      if (!data.enabled) {
        updateStatus(data.reason || "MCP is disabled", true);
        return;
      }
      if (!data.servers.length) {
        updateStatus("No MCP servers configured", true);
        return;
      }

      controlsEl.classList.remove("hidden");
      serverSelect.innerHTML = "";
      data.servers.forEach((server) => {
        const option = document.createElement("option");
        option.value = server.name;
        option.textContent = `${server.name} (${server.transport})`;
        option.dataset.description = server.description || "";
        serverSelect.appendChild(option);
      });
      updateStatus("Ready");
      await loadTools(serverSelect.value);
    } catch (err) {
      updateStatus("Unable to load MCP servers", true);
    }
  };

  const describeTool = (tool) => {
    descriptionEl.textContent = tool?.description || "No description provided.";
    if (tool?.input_schema) {
      schemaEl.textContent = JSON.stringify(tool.input_schema, null, 2);
      schemaEl.classList.remove("hidden");
    } else {
      schemaEl.textContent = "";
      schemaEl.classList.add("hidden");
    }
  };

  const loadTools = async (serverName) => {
    if (!serverName) return;
    updateStatus(`Loading tools for ${serverName}…`);
    try {
      const response = await fetch(`/mcp/servers/${encodeURIComponent(serverName)}/tools`);
      if (!response.ok) throw new Error("Failed to load tools");
      const tools = await response.json();
      toolSelect.innerHTML = "";
      if (!tools.length) {
        describeTool(null);
        updateStatus(`No tools available for ${serverName}`, true);
        return;
      }
      tools.forEach((tool, index) => {
        const option = document.createElement("option");
        option.value = tool.name;
        option.textContent = tool.name;
        option.dataset.description = tool.description || "";
        option.dataset.schema = tool.input_schema ? JSON.stringify(tool.input_schema) : "";
        toolSelect.appendChild(option);
        if (index === 0) {
          describeTool(tool);
        }
      });
      updateStatus(`Loaded ${tools.length} tool(s)`);
    } catch (err) {
      updateStatus(`Unable to load tools for ${serverName}`, true);
    }
  };

  const parseArgs = () => {
    const raw = (argsInput.value || "").trim();
    if (!raw) return {};
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return parsed;
      }
    } catch (err) {
      /* no-op handled below */
    }
    throw new Error("Arguments must be valid JSON");
  };

  const renderResult = (raw, html) => {
    if (html) {
      resultEl.innerHTML = html;
      return;
    }
    resultEl.textContent = raw || "Tool executed";
  };

  runButton?.addEventListener("click", async () => {
    const server = serverSelect.value;
    const tool = toolSelect.value;
    if (!server || !tool) return;
    let args = {};
    try {
      args = parseArgs();
    } catch (err) {
      updateStatus(err.message, true);
      return;
    }
    updateStatus(`Running ${tool} on ${server}…`);
    try {
      const response = await fetch(`/mcp/servers/${encodeURIComponent(server)}/tools/${encodeURIComponent(tool)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ args, session_id: sessionId }),
      });
      if (!response.ok) throw new Error("Tool execution failed");
      const data = await response.json();
      const rendered = data.message_html || renderMarkdown(data.result?.display);
      renderResult(data.result?.display, rendered);
      if (data.message_html) {
        appendAssistantBubble(data.message_html);
      }
      updateStatus("Tool completed");
    } catch (err) {
      updateStatus(err.message, true);
    }
  });

  serverSelect?.addEventListener("change", (event) => {
    const selected = event.target.value;
    loadTools(selected);
  });

  toolSelect?.addEventListener("change", () => {
    const option = toolSelect.options[toolSelect.selectedIndex];
    const schema = option?.dataset.schema;
    describeTool({
      description: option?.dataset.description || "",
      input_schema: schema ? JSON.parse(schema) : null,
    });
  });

  loadServers();
});
