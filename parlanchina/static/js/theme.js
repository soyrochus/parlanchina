(() => {
  const storageKey = "parlanchina-theme";
  const root = document.documentElement;

  const applyTheme = (mode) => {
    if (mode === "system") {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.classList.toggle("dark", prefersDark);
    } else {
      root.classList.toggle("dark", mode === "dark");
    }
    
    // Reinitialize Mermaid with new theme
    if (window.mermaid) {
      const isDark = root.classList.contains('dark');
      window.mermaid.initialize({ 
        startOnLoad: false, 
        theme: isDark ? 'dark' : 'default'
      });
      // Re-render any existing Mermaid diagrams
      window.mermaid.run();
    }
  };

  const saved = localStorage.getItem(storageKey) || "system";
  applyTheme(saved);

  // Backwards-compatible: support both button-based toggles and the new select.
  const toggleContainer = document.getElementById("theme-toggle");
  if (toggleContainer) {
    // Buttons (legacy)
    toggleContainer.querySelectorAll("button[data-theme]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const choice = btn.dataset.theme;
        localStorage.setItem(storageKey, choice);
        applyTheme(choice);
        // If a select exists, keep it in sync
        const sel = document.getElementById('theme-select');
        if (sel) sel.value = choice;
      });
    });

    // Select (new)
    const select = document.getElementById('theme-select');
    if (select) {
      // Initialize select to saved value
      select.value = saved;
      select.addEventListener('change', (e) => {
        const choice = e.target.value;
        localStorage.setItem(storageKey, choice);
        applyTheme(choice);
      });
    }
  }

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const current = localStorage.getItem(storageKey) || "system";
    if (current === "system") applyTheme(current);
  });
})();
