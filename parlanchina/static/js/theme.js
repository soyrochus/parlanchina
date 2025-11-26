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
  };

  const saved = localStorage.getItem(storageKey) || "system";
  applyTheme(saved);

  const toggleContainer = document.getElementById("theme-toggle");
  if (toggleContainer) {
    toggleContainer.querySelectorAll("button[data-theme]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const choice = btn.dataset.theme;
        localStorage.setItem(storageKey, choice);
        applyTheme(choice);
      });
    });
  }

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    const current = localStorage.getItem(storageKey) || "system";
    if (current === "system") applyTheme(current);
  });
})();
