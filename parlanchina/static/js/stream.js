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

  // Check if this is the first message by looking for actual message bubbles
  let isFirstMessage = messagesEl.querySelectorAll('.flex.justify-end, .flex.justify-start').length === 0;
  let titleCheckTimeout = null;
  
  // Get current session ID from form or URL
  const getCurrentSessionId = () => {
    return form?.dataset.sessionId || window.location.pathname.split('/').pop();
  };

  const runMermaid = () => {
    if (window.mermaid) {
      window.mermaid.run();
    }
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
    
    const messageWrapper = document.createElement("div");
    messageWrapper.className = "assistant-message-wrapper max-w-3xl rounded-2xl bg-white/80 dark:bg-slate-800/70 shadow-sm";
    
    const contentDiv = document.createElement("div");
    contentDiv.className = "prose prose-slate dark:prose-invert px-4 pt-3 pb-1";
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
        contentDiv.innerHTML = DOMPurify.sanitize(rendered);
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
        contentDiv.innerHTML = data.html;
        // Store the raw text in the message wrapper
        messageWrapper.setAttribute('data-raw-text', data.raw);
        runMermaid();
      } else {
        contentDiv.innerHTML = `<p class="text-sm text-red-500">Failed to save response.</p>`;
      }
    } catch (err) {
      contentDiv.innerHTML = `<p class="text-sm text-red-500">Error streaming response.</p>`;
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
