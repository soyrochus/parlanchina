(function () {
  const settingsButton = document.getElementById("settings-menu-button");
  const settingsMenu = document.getElementById("settings-menu");
  const triggers = {
    config: document.getElementById("settings-config"),
    about: document.getElementById("settings-about"),
  };
  const modals = {
    config: document.getElementById("config-modal"),
    about: document.getElementById("about-modal"),
  };

  if (
    !settingsButton ||
    !settingsMenu ||
    (!triggers.config && !triggers.about) ||
    (!modals.config && !modals.about)
  ) {
    return;
  }

  let menuOpen = false;
  let currentModal = null;

  const updateMenu = (open) => {
    menuOpen = open;
    settingsButton.setAttribute("aria-expanded", open ? "true" : "false");
    settingsMenu.classList.toggle("hidden", !open);
  };

  const openMenu = () => updateMenu(true);
  const closeMenu = () => updateMenu(false);

  const openModal = (name) => {
    const modal = modals[name];
    if (!modal) {
      return;
    }
    currentModal = name;
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("overflow-hidden");
  };

  const closeModal = (name = null) => {
    const targetName = name || currentModal;
    if (!targetName) {
      return;
    }
    const modal = modals[targetName];
    if (!modal) {
      return;
    }
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    if (currentModal === targetName) {
      currentModal = null;
      document.body.classList.remove("overflow-hidden");
    }
  };

  settingsButton.addEventListener("click", (event) => {
    event.stopPropagation();
    updateMenu(!menuOpen);
  });

  Object.entries(triggers).forEach(([name, trigger]) => {
    if (!trigger || !modals[name]) {
      return;
    }
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      closeMenu();
      openModal(name);
    });
  });

  document.addEventListener("click", (event) => {
    if (!menuOpen) {
      return;
    }
    if (!settingsMenu.contains(event.target) && event.target !== settingsButton) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (currentModal) {
        closeModal();
      } else if (menuOpen) {
        closeMenu();
      }
    }
  });

  document.querySelectorAll("[data-modal-backdrop]").forEach((backdrop) => {
    const modalName = backdrop.getAttribute("data-modal-backdrop");
    backdrop.addEventListener("click", () => closeModal(modalName));
  });

  document.querySelectorAll("[data-modal-close]").forEach((button) => {
    const modalName = button.getAttribute("data-modal-close");
    button.addEventListener("click", () => closeModal(modalName));
  });

  Object.entries(modals).forEach(([name, modal]) => {
    if (!modal) {
      return;
    }
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        closeModal(name);
      }
    });
  });
})();
