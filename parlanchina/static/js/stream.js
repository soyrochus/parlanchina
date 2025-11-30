document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  const messagesEl = document.getElementById("messages");
  const textarea = document.getElementById("message-input");
  const modelSelect = document.getElementById("model-select");
  const sessionTitleEl = document.querySelector("h1"); // Main session title
  
  const md = window.markdownit({
    linkify: true,
    breaks: true,
  });

  const toolPanel = document.getElementById("tool-panel");
  const toolListEl = document.getElementById("tool-list");
  const toolStatusEl = document.getElementById("tool-status");
  const toolSelectAllBtn = document.getElementById("tool-select-all");
  const toolClearAllBtn = document.getElementById("tool-clear-all");
  const toolApplyBtn = document.getElementById("tool-apply");
  const toolCancelBtn = document.getElementById("tool-cancel");
  const toolToggleBtn = document.getElementById("toolbox-toggle");
  const modeAskBtn = document.getElementById("mode-ask");
  const modeAgentBtn = document.getElementById("mode-agent");
  
  // Custom fence renderer for Mermaid diagrams
  const defaultFence = md.renderer.rules.fence;
  md.renderer.rules.fence = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const info = token.info ? token.info.trim() : '';
    
    if (info === 'mermaid') {
      const content = token.content;
      const escapedContent = content
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
      
      return `<div class="mermaid-container">` +
        `<button class="mermaid-zoom-btn" title="Zoom diagram">` +
        `<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">` +
        `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7"/>` +
        `</svg></button>` +
        `<pre class="mermaid" data-mermaid-source="${escapedContent}">${escapedContent}</pre>` +
        `</div>`;
    }
    
    return defaultFence(tokens, idx, options, env, self);
  };

  // Check if this is the first message by looking for actual message bubbles
  let isFirstMessage = messagesEl.querySelectorAll('.flex.justify-end, .flex.justify-start').length === 0;
  let titleCheckTimeout = null;
  
  // Get current session ID from form or URL
  const getCurrentSessionId = () => {
    return form?.dataset.sessionId || window.location.pathname.split('/').pop();
  };
  const currentSessionId = getCurrentSessionId();

  const toolState = {
    modeApplied: "ask",
    modeDraft: "ask",
    internal: [],
    mcp: [],
    appliedInternal: new Set(),
    appliedMcp: new Set(),
    draftInternal: new Set(),
    draftMcp: new Set(),
    mcpEnabled: true,
    serverCollapse: {},
    loaded: false,
    mcpReason: null,
  };

  const setToolStatus = (text, isError = false) => {
    if (!toolStatusEl) return;
    toolStatusEl.textContent = text;
    toolStatusEl.classList.toggle("text-red-500", isError);
    toolStatusEl.classList.toggle("dark:text-red-400", isError);
  };

  const handleToggleTool = (toolId, checked, category) => {
    const setRef = category === "internal" ? toolState.draftInternal : toolState.draftMcp;
    if (checked) {
      setRef.add(toolId);
    } else {
      setRef.delete(toolId);
    }
    const draftCount = toolState.draftInternal.size + (toolState.modeDraft === "agent" ? toolState.draftMcp.size : 0);
    setToolStatus(`${draftCount} tool(s) selected (draft)`);
  };

  const renderToolRows = () => {
    if (!toolListEl) return;
    toolListEl.innerHTML = "";

    const modeIsAgent = toolState.modeDraft === "agent";

    const makeCheckbox = (tool, checked, disabled, category) => {
      const row = document.createElement("label");
      row.className = `flex items-start gap-2 rounded-lg px-2 py-2 ${disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/60"}`;
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "mt-1 h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500 dark:border-slate-600 dark:bg-slate-800 dark:checked:bg-white";
      checkbox.checked = checked;
      checkbox.disabled = disabled;
      checkbox.dataset.toolId = tool.id;
      checkbox.addEventListener("change", (e) => {
        handleToggleTool(tool.id, e.target.checked, category);
      });
      const textWrapper = document.createElement("div");
      const label = document.createElement("p");
      label.className = "text-sm font-medium text-slate-800 dark:text-slate-100";
      label.textContent = tool.name;
      const desc = document.createElement("p");
      desc.className = "text-xs text-slate-500 dark:text-slate-400";
      desc.textContent = tool.description || tool.id;
      textWrapper.appendChild(label);
      textWrapper.appendChild(desc);
      row.appendChild(checkbox);
      row.appendChild(textWrapper);
      return row;
    };

    const internalSection = document.createElement("div");
    const internalHeader = document.createElement("div");
    internalHeader.className = "flex items-center justify-between";
    internalHeader.innerHTML = `<p class="text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">Internal tools</p>`;
    internalSection.appendChild(internalHeader);
    const internalList = document.createElement("div");
    internalList.className = "mt-2 space-y-1";
    toolState.internal
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name))
      .forEach((tool) => {
        const row = makeCheckbox(tool, toolState.draftInternal.has(tool.id), false, "internal");
        internalList.appendChild(row);
      });
    internalSection.appendChild(internalList);
    toolListEl.appendChild(internalSection);

    const mcpSection = document.createElement("div");
    mcpSection.className = "mt-3";
    const mcpHeader = document.createElement("div");
    mcpHeader.className = "flex items-center justify-between";
    const mcpLabel = document.createElement("p");
    mcpLabel.className = "text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300";
    mcpLabel.textContent = "MCP tools";
    mcpHeader.appendChild(mcpLabel);
    const mcpNote = document.createElement("p");
    mcpNote.className = "text-xs text-slate-500 dark:text-slate-400";
    if (!toolState.mcpEnabled) {
      mcpNote.textContent = toolState.mcpReason || "MCP disabled";
    } else if (!modeIsAgent) {
      mcpNote.textContent = "Enable Agent mode to use MCP tools";
    }
    if (mcpNote.textContent) {
      mcpHeader.appendChild(mcpNote);
    }
    mcpSection.appendChild(mcpHeader);

    const disableMcp = !toolState.mcpEnabled || !modeIsAgent;
    const grouped = toolState.mcp.reduce((acc, tool) => {
      acc[tool.server] = acc[tool.server] || [];
      acc[tool.server].push(tool);
      return acc;
    }, {});

    Object.entries(grouped).forEach(([server, tools]) => {
      const details = document.createElement("details");
      details.className = `rounded-lg border border-slate-200/70 bg-white/60 px-3 py-2 shadow-sm dark:border-slate-800 dark:bg-slate-900/40 ${disableMcp ? "opacity-60" : ""}`;
      details.open = toolState.serverCollapse[server] !== false;
      details.addEventListener("toggle", () => {
        toolState.serverCollapse[server] = details.open;
      });

      const summary = document.createElement("summary");
      summary.className = "flex cursor-pointer select-none items-center justify-between gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100";
      summary.innerHTML = `<span>${server}</span><span class="text-xs text-slate-500 dark:text-slate-400">${tools.length} tool${tools.length === 1 ? "" : "s"}</span>`;
      details.appendChild(summary);

      const list = document.createElement("div");
      list.className = "mt-2 space-y-1";
      tools
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name))
        .forEach((tool) => {
          const row = makeCheckbox(tool, toolState.draftMcp.has(tool.id), disableMcp, "mcp");
          list.appendChild(row);
        });
      details.appendChild(list);
      mcpSection.appendChild(details);
    });

    toolListEl.appendChild(mcpSection);
  };

  const loadTools = async () => {
    if (!toolPanel || !currentSessionId) return;
    setToolStatus("Loading tools…");
    try {
      const res = await fetch(`/mcp/tools?session_id=${encodeURIComponent(currentSessionId)}`);
      if (!res.ok) throw new Error("Failed to load tools");
      const data = await res.json();
      toolState.modeApplied = data.mode || "ask";
      toolState.modeDraft = toolState.modeApplied;
      toolState.internal = data.internal || [];
      toolState.mcp = data.mcp || [];
      toolState.mcpEnabled = data.mcp_enabled !== false;
      toolState.mcpReason = data.reason || null;
      toolState.appliedInternal = new Set(
        (toolState.internal || []).filter((tool) => tool.applied).map((tool) => tool.id)
      );
      toolState.appliedMcp = new Set((toolState.mcp || []).filter((tool) => tool.applied).map((tool) => tool.id));
      toolState.draftInternal = new Set(toolState.appliedInternal);
      toolState.draftMcp = new Set(toolState.appliedMcp);
      renderToolRows();
      const appliedCount =
        toolState.appliedInternal.size + (toolState.modeApplied === "agent" ? toolState.appliedMcp.size : 0);
      if (!toolState.mcpEnabled) {
        setToolStatus(toolState.mcpReason || "MCP disabled", true);
      } else {
        setToolStatus(`${appliedCount} tool(s) applied in ${toolState.modeApplied} mode`);
      }
      updateModeButtons();
    } catch (err) {
      console.debug("Unable to load tools", err);
      toolState.internal = [];
      toolState.mcp = [];
      toolState.appliedInternal = new Set();
      toolState.appliedMcp = new Set();
      toolState.draftInternal = new Set();
      toolState.draftMcp = new Set();
      setToolStatus("Unable to load tools", true);
      renderToolRows();
    } finally {
      toolState.loaded = true;
    }
  };

  const updateModeButtons = () => {
    if (!modeAskBtn || !modeAgentBtn) return;
    const activeClass = "bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-sm";
    const inactiveClass = "text-slate-700 dark:text-slate-200";
    const setBtn = (btn, active) => {
      btn.className = `rounded-md px-2 py-1 ${active ? activeClass : inactiveClass}`;
    };
    setBtn(modeAskBtn, toolState.modeDraft === "ask");
    setBtn(modeAgentBtn, toolState.modeDraft === "agent");
  };

  const runMermaid = () => {
    if (window.mermaid) {
      return window.mermaid.run();
    }
    return Promise.resolve();
  };
  
  const wrapMermaidDiagrams = (container) => {
    // Find all mermaid pre elements that aren't already wrapped
    const mermaidPres = container.querySelectorAll('pre.mermaid');
    mermaidPres.forEach(pre => {
      // Skip if already wrapped
      if (pre.parentElement && pre.parentElement.classList.contains('mermaid-container')) {
        return;
      }
      
      // Store the mermaid source
      const source = pre.textContent;
      
      // Create wrapper
      const wrapper = document.createElement('div');
      wrapper.className = 'mermaid-container';
      
      // Create zoom button
      const button = document.createElement('button');
      button.className = 'mermaid-zoom-btn';
      button.title = 'Zoom diagram';
      button.innerHTML = `
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7"/>
        </svg>
      `;
      
      // Store source as data attribute
      pre.setAttribute('data-mermaid-source', source);
      
      // Wrap the pre element
      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(button);
      wrapper.appendChild(pre);
      ensureRenderingOverlay(wrapper);
    });

    // Ensure overlays exist for any pre-existing wrapped elements
    container.querySelectorAll('.mermaid-container').forEach(wrapper => ensureRenderingOverlay(wrapper));
    // Refresh overlay visibility if message state already tracked
    const messageWrapper = container.closest('.assistant-message-wrapper');
    if (messageWrapper) {
      refreshOverlayVisibility(messageWrapper);
    }
  };

  const containsMermaidFence = (text) => /```mermaid/i.test(text);
  const hasCompleteMermaidBlock = (text) => /```mermaid[\s\S]*?```/i.test(text);

  const ensureRenderingOverlay = (mermaidContainer) => {
    if (!mermaidContainer) return null;
    let overlay = mermaidContainer.querySelector('.rendering-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'rendering-overlay';
      overlay.innerHTML = `
        <div class="rendering-indicator">
          <span class="rendering-dot"></span>
          <span class="rendering-text">Rendering diagram...</span>
        </div>
      `;
      mermaidContainer.appendChild(overlay);
    }
    return overlay;
  };

  const refreshOverlayVisibility = (messageWrapper) => {
    if (!messageWrapper) return;
    const isRendering = messageWrapper.dataset.isRenderingHeavyContent === 'true';
    const isPending = messageWrapper.dataset.isMermaidPending === 'true';
    const mermaidContainers = messageWrapper.querySelectorAll('.mermaid-container');
    mermaidContainers.forEach(container => {
      const overlay = ensureRenderingOverlay(container);
      if (!overlay) return;
      const shouldShow = isRendering || isPending;
      overlay.classList.toggle('visible', shouldShow);
      container.classList.toggle('rendering-pending', isPending);
    });
  };

  const setRenderingState = (messageWrapper, isRendering) => {
    if (!messageWrapper) return;
    messageWrapper.dataset.isRenderingHeavyContent = isRendering ? 'true' : 'false';
    refreshOverlayVisibility(messageWrapper);
  };

  const setMermaidPendingState = (messageWrapper, isPending) => {
    if (!messageWrapper) return;
    messageWrapper.dataset.isMermaidPending = isPending ? 'true' : 'false';
    refreshOverlayVisibility(messageWrapper);
  };

  const ensureImageWrapper = (imgElement) => {
    if (!imgElement) return null;
    let wrapper = imgElement.closest('.generated-image-wrapper');
    if (!wrapper) {
      wrapper = document.createElement('div');
      wrapper.className = 'generated-image-wrapper';
      imgElement.parentNode.insertBefore(wrapper, imgElement);
      wrapper.appendChild(imgElement);
    }

    if (!wrapper.querySelector('.image-zoom-btn')) {
      const zoomBtn = document.createElement('button');
      zoomBtn.className = 'image-zoom-btn';
      zoomBtn.title = 'Zoom image';
      zoomBtn.innerHTML = `
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7"/>
        </svg>
      `;
      wrapper.appendChild(zoomBtn);
    }

    let overlay = wrapper.querySelector('.rendering-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'rendering-overlay image-overlay';
      overlay.innerHTML = `
        <div class="rendering-indicator">
          <span class="rendering-dot"></span>
          <span class="rendering-text">Generating image...</span>
        </div>
      `;
      wrapper.appendChild(overlay);
    }

    return wrapper;
  };

  const wrapGeneratedImages = (container, messageWrapper, pendingImages = []) => {
    if (!container) return;
    const pendingSet = new Set(
      pendingImages.filter((img) => img.status !== 'done').map((img) => img.url)
    );

    const images = container.querySelectorAll('img');
    images.forEach((img) => {
      const wrapper = ensureImageWrapper(img);
      const overlay = wrapper?.querySelector('.rendering-overlay');
      const src = img.getAttribute('src');
      const isPending = pendingSet.has(src);

      if (!img.dataset.boundLoad) {
        img.dataset.boundLoad = 'true';
        img.addEventListener('load', () => {
          const matching = pendingImages.find((item) => item.url === src);
          if (matching) matching.status = 'done';
          overlay?.classList.remove('visible');
        });
        img.addEventListener('error', () => {
          if (overlay) {
            overlay.classList.add('visible');
            const text = overlay.querySelector('.rendering-text');
            if (text) text.textContent = 'Failed to load image';
          }
        });
      }

      if (overlay) {
        overlay.classList.toggle('visible', isPending);
        wrapper.classList.toggle('rendering-pending', isPending);
      }
    });

    messageWrapper.dataset.isRenderingImage = pendingSet.size ? 'true' : 'false';
  };

  const checkForTitleUpdate = async (sessionId) => {
    try {
      const response = await fetch(`/chat/${sessionId}/info`);
      if (response.ok) {
        const data = await response.json();
        const currentTitle = sessionTitleEl.textContent;
        if (data.title !== currentTitle && data.title !== "New chat") {
          // Update main title
          sessionTitleEl.textContent = data.title;
          
          // Update sidebar title for current session
          const sidebarTitleEl = document.querySelector(`[data-session-id="${sessionId}"] .session-title`);
          if (sidebarTitleEl) {
            sidebarTitleEl.textContent = data.title;
          }
          
          // Update page title
          document.title = `${data.title} - Parlanchina`;
        }
      }
    } catch (err) {
      console.debug("Failed to check for title update:", err);
    }
  };

  const initializeExistingMessages = () => {
    document.querySelectorAll('.assistant-message-wrapper').forEach((wrapper) => {
      const content = wrapper.querySelector('.prose');
      if (content) {
        wrapMermaidDiagrams(content);
        wrapGeneratedImages(content, wrapper, []);
      }
    });
  };

  runMermaid();
  initializeExistingMessages();

  const appendUserBubble = (content) => {
    const wrapper = document.createElement("div");
    wrapper.className = "flex justify-end";
    wrapper.innerHTML = `<div class="max-w-7xl rounded-2xl bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-4 py-3 shadow-sm whitespace-pre-wrap">${escapeHtml(content)}</div>`;
    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  const appendAssistantBubble = () => {
    const wrapper = document.createElement("div");
    wrapper.className = "flex justify-start";
    
    const messageWrapper = document.createElement("div");
    messageWrapper.className = "assistant-message-wrapper max-w-7xl rounded-2xl bg-white/80 dark:bg-slate-800/70 shadow-sm";
    messageWrapper.dataset.isRenderingHeavyContent = 'false';
    messageWrapper.dataset.hasMermaid = 'false';
    messageWrapper.dataset.isMermaidPending = 'false';
    messageWrapper.dataset.isRenderingImage = 'false';
    messageWrapper.dataset.imageIndicatorShown = 'false';

    const contentDiv = document.createElement("div");
    contentDiv.className = "prose prose-slate dark:prose-invert max-w-none px-4 pt-3 pb-1";
    contentDiv.innerHTML = `<p class="text-sm text-slate-500">Thinking...</p>`;
    
    const footerDiv = document.createElement("div");
    footerDiv.className = "px-4 pb-3 pt-1 flex items-center";
    footerDiv.innerHTML = `
      <button class="copy-btn text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 transition-colors" title="Copy to clipboard">
        <svg class="copy-icon w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
        </svg>
        <svg class="check-icon w-4 h-4 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
        </svg>
      </button>
    `;
    
    messageWrapper.appendChild(contentDiv);
    messageWrapper.appendChild(footerDiv);
    wrapper.appendChild(messageWrapper);
    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    
    return { contentDiv, messageWrapper };
  };

  const escapeHtml = (unsafe) => {
    const map = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return unsafe.replace(/[&<>"']/g, (m) => map[m]);
  };

  const streamAssistant = async (sessionId, model) => {
    const { contentDiv, messageWrapper } = appendAssistantBubble();
    let buffer = "";
    let hasMermaid = false;
    let hasCompleteMermaid = false;
    let pendingImages = [];
    let collectedImages = [];
    let remainder = "";

    const markMermaidRendering = () => {
      if (!hasMermaid && containsMermaidFence(buffer)) {
        hasMermaid = true;
        messageWrapper.dataset.hasMermaid = 'true';
      }
      if (hasMermaid) {
        hasCompleteMermaid = hasCompleteMermaidBlock(buffer);
        setMermaidPendingState(messageWrapper, !hasCompleteMermaid);
      }
    };

    const renderBuffer = () => {
      const rendered = md.render(buffer);
      const safeHtml = DOMPurify.sanitize(rendered, {
        ADD_TAGS: ['button', 'svg', 'path', 'img'],
        ADD_ATTR: [
          'stroke',
          'stroke-linecap',
          'stroke-linejoin',
          'stroke-width',
          'd',
          'viewBox',
          'fill',
          'data-mermaid-source',
          'src',
          'alt',
          'title',
          'loading',
          'decoding',
        ],
      });
      const showImageIndicator =
        messageWrapper.dataset.imageIndicatorShown === 'true' &&
        messageWrapper.dataset.isRenderingImage === 'true';
      const prefix = showImageIndicator
        ? '<p class="text-sm text-slate-500 mb-2">Generating image...</p>'
        : '';
      contentDiv.innerHTML = prefix + safeHtml;
      wrapMermaidDiagrams(contentDiv);
      wrapGeneratedImages(contentDiv, messageWrapper, pendingImages);
      if (hasMermaid) {
        setRenderingState(messageWrapper, true);
      }
      runMermaid();
      messagesEl.scrollTop = messagesEl.scrollHeight;
    };

    const handleTextDelta = (delta) => {
      if (!delta) return;
      buffer += delta;
      markMermaidRendering();
      renderBuffer();
    };

    const handleImageEvent = (payload) => {
      if (!payload || !payload.url) return;
      const altText = payload.alt_text || 'Generated image';
      const markdown = payload.markdown || `\n\n![${altText}](${payload.url})\n`;
      if (messageWrapper.dataset.imageIndicatorShown !== 'true') {
        messageWrapper.dataset.imageIndicatorShown = 'true';
      }
      buffer += markdown;
      pendingImages.push({ url: payload.url, alt_text: altText, status: 'pending' });
      collectedImages.push({ url: payload.url, alt_text: altText });
      messageWrapper.dataset.hasImages = 'true';
      messageWrapper.dataset.isRenderingImage = 'true';
      renderBuffer();
    };

    try {
      const response = await fetch(`/chat/${sessionId}/stream?model=${encodeURIComponent(model || "")}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        remainder += decoder.decode(value, { stream: true });
        const parts = remainder.split(/\n/);
        remainder = parts.pop() || "";
        for (const part of parts) {
          const line = part.trim();
          if (!line) continue;
          let payload;
          try {
            payload = JSON.parse(line);
          } catch (err) {
            console.debug('Failed to parse stream chunk', err);
            continue;
          }

          switch (payload.type) {
            case 'text_delta':
              handleTextDelta(payload.text || '');
              break;
            case 'image_start':
              messageWrapper.dataset.imageIndicatorShown = 'true';
              messageWrapper.dataset.isRenderingImage = 'true';
              renderBuffer();
              break;
            case 'image':
              handleImageEvent(payload);
              break;
            case 'error':
              contentDiv.innerHTML = `<p class="text-sm text-red-500">${payload.message || 'Streaming error.'}</p>`;
              break;
            case 'text_done':
              if (payload.text) {
                buffer = payload.text;
                markMermaidRendering();
                renderBuffer();
              }
              if (Array.isArray(payload.images) && payload.images.length) {
                collectedImages = payload.images;
                pendingImages = payload.images.map((img) => ({ ...img, status: 'done' }));
                wrapGeneratedImages(contentDiv, messageWrapper, pendingImages);
              }
              break;
            default:
              break;
          }
        }
      }
      // Ensure we didn't miss mermaid detection during streaming
      markMermaidRendering();
      const finalizeResponse = await fetch(`/chat/${sessionId}/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: buffer, model, images: collectedImages }),
      });
      if (finalizeResponse.ok) {
        const data = await finalizeResponse.json();
        contentDiv.innerHTML = data.html;
        // Store the raw text in the message wrapper
        messageWrapper.setAttribute('data-raw-text', data.raw);
        wrapMermaidDiagrams(contentDiv);
        pendingImages = collectedImages.map((img) => ({ ...img, status: 'done' }));
        wrapGeneratedImages(contentDiv, messageWrapper, pendingImages);
        if (hasMermaid) {
          try {
            await runMermaid();
          } finally {
            setMermaidPendingState(messageWrapper, false);
            setRenderingState(messageWrapper, false);
          }
        } else {
          runMermaid();
        }
        messageWrapper.dataset.isRenderingImage = 'false';
      } else {
        contentDiv.innerHTML = `<p class="text-sm text-red-500">Failed to save response.</p>`;
        if (hasMermaid) {
          setMermaidPendingState(messageWrapper, false);
          setRenderingState(messageWrapper, false);
        }
      }
    } catch (err) {
      contentDiv.innerHTML = `<p class="text-sm text-red-500">Error streaming response.</p>`;
    } finally {
      if (hasMermaid) {
        setMermaidPendingState(messageWrapper, false);
        if (messageWrapper.dataset.isRenderingHeavyContent === 'true') {
          setRenderingState(messageWrapper, false);
        }
      }
      messageWrapper.dataset.isRenderingImage =
        pendingImages.some((img) => img.status !== 'done') ? 'true' : 'false';
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  };

  const triggerFormSubmit = () => {
    if (!form) return;
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
  };

  if (form) {
    if (textarea) {
      textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          triggerFormSubmit();
        }
      });
    }

    const showToolPanel = async () => {
      await loadTools();
      if (toolPanel) {
        toolPanel.classList.remove("hidden");
      }
    };

    const hideToolPanel = () => {
      if (toolPanel) {
        toolPanel.classList.add("hidden");
        setToolStatus("Toolbox closed");
      }
    };

    toolToggleBtn?.addEventListener("click", async (e) => {
      e.preventDefault();
      await showToolPanel();
    });

    modeAskBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      toolState.modeDraft = "ask";
      updateModeButtons();
      renderToolRows();
    });
    modeAgentBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      toolState.modeDraft = "agent";
      updateModeButtons();
      renderToolRows();
    });

    toolSelectAllBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      toolState.internal.forEach((tool) => toolState.draftInternal.add(tool.id));
      if (toolState.modeDraft === "agent" && toolState.mcpEnabled) {
        toolState.mcp.forEach((tool) => toolState.draftMcp.add(tool.id));
      }
      renderToolRows();
      const totalDraft =
        toolState.draftInternal.size + (toolState.modeDraft === "agent" ? toolState.draftMcp.size : 0);
      setToolStatus(`${totalDraft} tool(s) selected (draft)`);
    });
    toolClearAllBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      toolState.draftInternal.clear();
      toolState.draftMcp.clear();
      renderToolRows();
      setToolStatus("No tools selected (draft)");
    });
    toolCancelBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      toolState.draftInternal = new Set(toolState.appliedInternal);
      toolState.draftMcp = new Set(toolState.appliedMcp);
      toolState.modeDraft = toolState.modeApplied;
      renderToolRows();
      updateModeButtons();
      hideToolPanel();
    });
    toolApplyBtn?.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!currentSessionId) return;
      try {
        const res = await fetch("/mcp/tools/selection", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: currentSessionId,
            mode: toolState.modeDraft,
            enabled_internal_tools: Array.from(toolState.draftInternal),
            enabled_mcp_tools: Array.from(toolState.draftMcp),
          }),
        });
        if (res.ok) {
          const data = await res.json();
          toolState.modeApplied = data.mode || toolState.modeDraft;
          toolState.modeDraft = toolState.modeApplied;
          toolState.internal = data.internal || toolState.internal;
          toolState.mcp = data.mcp || toolState.mcp;
          toolState.appliedInternal = new Set(
            (data.internal || []).filter((tool) => tool.applied).map((tool) => tool.id)
          );
          toolState.appliedMcp = new Set((data.mcp || []).filter((tool) => tool.applied).map((tool) => tool.id));
          toolState.draftInternal = new Set(toolState.appliedInternal);
          toolState.draftMcp = new Set(toolState.appliedMcp);
          renderToolRows();
          updateModeButtons();
          const appliedCount =
            toolState.appliedInternal.size + (toolState.modeApplied === "agent" ? toolState.appliedMcp.size : 0);
          setToolStatus(`${appliedCount} tool(s) applied in ${toolState.modeApplied} mode`);
          hideToolPanel();
        } else {
          setToolStatus("Failed to apply selection", true);
        }
      } catch (err) {
        console.debug("Failed to apply tools", err);
        setToolStatus("Failed to apply selection", true);
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const sessionId = form.dataset.sessionId;
      const content = (textarea.value || "").trim();
      if (!content) return;
      const model = modelSelect?.value || modelSelect?.dataset.defaultModel || "";
      const payload = { message: content, model };

      appendUserBubble(content);
      textarea.value = "";

      await fetch(`/chat/${sessionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      // If this was the first message, start checking for title updates
      if (isFirstMessage) {
        isFirstMessage = false;
        // Start checking for title updates after a short delay
        setTimeout(() => {
          const checkTitle = async () => {
            await checkForTitleUpdate(sessionId);
            // Continue checking every 2 seconds for up to 30 seconds
            titleCheckTimeout = setTimeout(checkTitle, 2000);
          };
          checkTitle();
          // Stop checking after 30 seconds
          setTimeout(() => {
            if (titleCheckTimeout) {
              clearTimeout(titleCheckTimeout);
              titleCheckTimeout = null;
            }
          }, 30000);
        }, 1000);
      }

      streamAssistant(sessionId, model);
    });
  }

  // Session management functionality
  const initSessionManagement = () => {
    // Handle menu trigger clicks
    document.addEventListener('click', async (e) => {
      // Menu trigger
      if (e.target.closest('.session-menu-trigger')) {
        e.preventDefault();
        e.stopPropagation();
        
        // Close all other menus
        document.querySelectorAll('.session-menu').forEach(menu => {
          menu.classList.add('hidden');
        });
        
        // Show this menu
        const trigger = e.target.closest('.session-menu-trigger');
        const menu = trigger.parentElement.querySelector('.session-menu');
        menu.classList.remove('hidden');
        return;
      }
      
      // Rename button
      if (e.target.closest('.rename-btn')) {
        e.preventDefault();
        const sessionId = e.target.closest('.rename-btn').dataset.sessionId;
        const sessionItem = e.target.closest('.session-item');
        const currentTitle = sessionItem.querySelector('.session-title').textContent;
        const renameContainer = sessionItem.querySelector('.rename-input-container');
        const renameInput = sessionItem.querySelector('.rename-input');
        
        // Hide menu and show rename input
        sessionItem.querySelector('.session-menu').classList.add('hidden');
        renameContainer.classList.remove('hidden');
        renameInput.value = currentTitle;
        renameInput.focus();
        renameInput.select();
        return;
      }
      
      // Delete button
      if (e.target.closest('.delete-btn')) {
        e.preventDefault();
        const sessionId = e.target.closest('.delete-btn').dataset.sessionId;
        const sessionTitle = e.target.closest('.session-item').querySelector('.session-title').textContent;
        
        if (confirm(`Are you sure you want to delete "${sessionTitle}"?`)) {
          try {
            const response = await fetch(`/chat/${sessionId}`, {
              method: 'DELETE'
            });
            
            if (response.ok) {
              // Remove from sidebar
              e.target.closest('.session-item').remove();
              
              // If we're viewing this session, redirect to home
              if (window.location.pathname.includes(sessionId)) {
                window.location.href = '/';
              }
            } else {
              alert('Failed to delete session.');
            }
          } catch (err) {
            alert('Error deleting session.');
          }
        }
        
        // Hide menu
        e.target.closest('.session-item').querySelector('.session-menu').classList.add('hidden');
        return;
      }
      
      // Rename save button
      if (e.target.closest('.rename-save')) {
        e.preventDefault();
        const sessionId = e.target.closest('.rename-save').dataset.sessionId;
        const sessionItem = e.target.closest('.session-item');
        const renameInput = sessionItem.querySelector('.rename-input');
        const newTitle = renameInput.value.trim();
        
        if (!newTitle) {
          alert('Title cannot be empty.');
          return;
        }
        
        try {
          const response = await fetch(`/chat/${sessionId}/rename`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle })
          });
          
          if (response.ok) {
            // Update title in sidebar
            sessionItem.querySelector('.session-title').textContent = newTitle;
            
            // Update main title if we're viewing this session
            if (window.location.pathname.includes(sessionId)) {
              sessionTitleEl.textContent = newTitle;
              document.title = `${newTitle} - Parlanchina`;
            }
            
            // Hide rename input
            sessionItem.querySelector('.rename-input-container').classList.add('hidden');
          } else {
            alert('Failed to rename session.');
          }
        } catch (err) {
          alert('Error renaming session.');
        }
        return;
      }
      
      // Rename cancel button
      if (e.target.closest('.rename-cancel')) {
        e.preventDefault();
        const sessionItem = e.target.closest('.session-item');
        sessionItem.querySelector('.rename-input-container').classList.add('hidden');
        return;
      }
      
      // Click outside - close all menus
      if (!e.target.closest('.session-menu') && !e.target.closest('.session-menu-trigger')) {
        document.querySelectorAll('.session-menu').forEach(menu => {
          menu.classList.add('hidden');
        });
      }
    });
    
    // Handle Enter key in rename input
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target.classList.contains('rename-input')) {
        e.target.closest('.session-item').querySelector('.rename-save').click();
      }
      if (e.key === 'Escape' && e.target.classList.contains('rename-input')) {
        e.target.closest('.session-item').querySelector('.rename-cancel').click();
      }
    });
  };
  
  // Initialize session management
  initSessionManagement();
  
  // Copy to clipboard functionality
  const initCopyButtons = () => {
    document.addEventListener('click', async (e) => {
      const copyBtn = e.target.closest('.copy-btn');
      if (!copyBtn) return;
      
      e.preventDefault();
      
      // Get the message wrapper that contains the raw text
      const messageWrapper = copyBtn.closest('.assistant-message-wrapper');
      if (!messageWrapper) return;
      
      const rawText = messageWrapper.getAttribute('data-raw-text');
      if (!rawText) return;
      
      try {
        // Copy to clipboard
        await navigator.clipboard.writeText(rawText);
        
        // Visual feedback: swap icons
        const copyIcon = copyBtn.querySelector('.copy-icon');
        const checkIcon = copyBtn.querySelector('.check-icon');
        
        if (copyIcon && checkIcon) {
          copyIcon.classList.add('hidden');
          checkIcon.classList.remove('hidden');
          
          // Revert after 2 seconds
          setTimeout(() => {
            copyIcon.classList.remove('hidden');
            checkIcon.classList.add('hidden');
          }, 2000);
        }
      } catch (err) {
        console.error('Failed to copy to clipboard:', err);
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = rawText;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
          document.execCommand('copy');
          // Still show feedback on success
          const copyIcon = copyBtn.querySelector('.copy-icon');
          const checkIcon = copyBtn.querySelector('.check-icon');
          if (copyIcon && checkIcon) {
            copyIcon.classList.add('hidden');
            checkIcon.classList.remove('hidden');
            setTimeout(() => {
              copyIcon.classList.remove('hidden');
              checkIcon.classList.add('hidden');
            }, 2000);
          }
        } catch (err2) {
          console.error('Fallback copy also failed:', err2);
        }
        document.body.removeChild(textarea);
      }
    });
  };
  
  // Initialize copy buttons
  initCopyButtons();
});
