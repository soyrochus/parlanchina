(function () {
  const settingsButton = document.getElementById("settings-menu-button");
  const settingsMenu = document.getElementById("settings-menu");
  const aboutTrigger = document.getElementById("settings-about");
  const aboutModal = document.getElementById("about-modal");

  if (!settingsButton || !settingsMenu || !aboutTrigger || !aboutModal) {
    return;
  }

  const backdrop = aboutModal.querySelector("[data-about-backdrop]");
  const closeButtons = aboutModal.querySelectorAll("[data-close-about]");

  let menuOpen = false;
  let modalOpen = false;

  const updateMenu = (open) => {
    menuOpen = open;
    settingsButton.setAttribute("aria-expanded", open ? "true" : "false");
    settingsMenu.classList.toggle("hidden", !open);
  };

  const openMenu = () => updateMenu(true);
  const closeMenu = () => updateMenu(false);

  const openModal = () => {
    modalOpen = true;
    aboutModal.classList.remove("hidden");
    aboutModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("overflow-hidden");
  };

  const closeModal = () => {
    modalOpen = false;
    aboutModal.classList.add("hidden");
    aboutModal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("overflow-hidden");
  };

  settingsButton.addEventListener("click", (event) => {
    event.stopPropagation();
    updateMenu(!menuOpen);
  });

  aboutTrigger.addEventListener("click", (event) => {
    event.preventDefault();
    closeMenu();
    openModal();
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
      if (modalOpen) {
        closeModal();
      } else if (menuOpen) {
        closeMenu();
      }
    }
  });

  if (backdrop) {
    backdrop.addEventListener("click", closeModal);
  }

  closeButtons.forEach((button) => {
    button.addEventListener("click", closeModal);
  });

  aboutModal.addEventListener("click", (event) => {
    if (event.target === aboutModal) {
      closeModal();
    }
  });
})();
