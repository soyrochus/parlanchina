document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  const messagesEl = document.getElementById("messages");
  const textarea = document.getElementById("message-input");
  const modelSelect = document.getElementById("model-select");
  const md = window.markdownit({
    linkify: true,
    breaks: true,
  });

  const runMermaid = () => {
    if (window.mermaid) {
      window.mermaid.run();
    }
  };

  runMermaid();

  const appendUserBubble = (content) => {
    const wrapper = document.createElement("div");
    wrapper.className = "flex justify-end";
    wrapper.innerHTML = `<div class="max-w-3xl rounded-2xl bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-4 py-3 shadow-sm whitespace-pre-wrap">${escapeHtml(content)}</div>`;
    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  const appendAssistantBubble = () => {
    const wrapper = document.createElement("div");
    wrapper.className = "flex justify-start";
    const bubble = document.createElement("div");
    bubble.className = "prose prose-slate dark:prose-invert max-w-3xl rounded-2xl bg-white/80 dark:bg-slate-800/70 px-4 py-3 shadow-sm";
    bubble.innerHTML = `<p class="text-sm text-slate-500">Thinking...</p>`;
    wrapper.appendChild(bubble);
    messagesEl.appendChild(wrapper);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return bubble;
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
    const bubble = appendAssistantBubble();
    let buffer = "";
    try {
      const response = await fetch(`/chat/${sessionId}/stream?model=${encodeURIComponent(model || "")}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;
        const rendered = md.render(buffer);
        bubble.innerHTML = DOMPurify.sanitize(rendered);
        runMermaid();
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
      const finalizeResponse = await fetch(`/chat/${sessionId}/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: buffer, model }),
      });
      if (finalizeResponse.ok) {
        const data = await finalizeResponse.json();
        bubble.innerHTML = data.html;
        runMermaid();
      } else {
        bubble.innerHTML = `<p class="text-sm text-red-500">Failed to save response.</p>`;
      }
    } catch (err) {
      bubble.innerHTML = `<p class="text-sm text-red-500">Error streaming response.</p>`;
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const sessionId = form.dataset.sessionId;
      const content = (textarea.value || "").trim();
      if (!content) return;
      const model = modelSelect?.value || modelSelect?.dataset.defaultModel || "";

      appendUserBubble(content);
      textarea.value = "";

      await fetch(`/chat/${sessionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: content, model }),
      });

      streamAssistant(sessionId, model);
    });
  }
});
