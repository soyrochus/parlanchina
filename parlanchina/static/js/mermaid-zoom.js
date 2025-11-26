(() => {
  const modal = document.getElementById('mermaid-modal');
  const modalBody = document.getElementById('mermaid-modal-body');
  const closeBtn = document.getElementById('mermaid-modal-close');
  const zoomSlider = document.getElementById('mermaid-zoom-slider');
  const zoomValue = document.getElementById('mermaid-zoom-value');
  
  let currentDiagramContainer = null;
  
  const openModal = async (mermaidSource) => {
    // Clear previous content
    modalBody.innerHTML = '';
    
    // Create a container for the diagram to apply zoom
    const container = document.createElement('div');
    container.className = 'mermaid-diagram-container';
    container.style.transformOrigin = 'center center';
    container.style.transition = 'transform 0.2s ease';
    
    // Create a new pre element with the mermaid source
    const pre = document.createElement('pre');
    pre.className = 'mermaid';
    pre.textContent = mermaidSource;
    container.appendChild(pre);
    modalBody.appendChild(container);
    
    currentDiagramContainer = container;
    
    // Reset zoom slider
    zoomSlider.value = 100;
    zoomValue.textContent = '100%';
    container.style.transform = 'scale(1)';
    
    // Show modal
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    
    // Render the mermaid diagram
    if (window.mermaid) {
      try {
        await window.mermaid.run({ nodes: [pre] });
      } catch (err) {
        console.error('Failed to render Mermaid diagram in modal:', err);
      }
    }
  };
  
  const closeModal = () => {
    modal.classList.add('hidden');
    document.body.style.overflow = '';
    modalBody.innerHTML = '';
    currentDiagramContainer = null;
  };
  
  // Zoom slider handler
  zoomSlider.addEventListener('input', (e) => {
    const zoomLevel = e.target.value;
    zoomValue.textContent = `${zoomLevel}%`;
    
    if (currentDiagramContainer) {
      const scale = zoomLevel / 100;
      currentDiagramContainer.style.transform = `scale(${scale})`;
    }
  });
  
  // Close button handler
  closeBtn.addEventListener('click', closeModal);
  
  // Close on backdrop click
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      closeModal();
    }
  });
  
  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
      closeModal();
    }
  });
  
  // Handle zoom button clicks
  document.addEventListener('click', (e) => {
    const zoomBtn = e.target.closest('.mermaid-zoom-btn');
    if (!zoomBtn) return;
    
    e.preventDefault();
    e.stopPropagation();
    
    // Find the associated mermaid pre element
    const container = zoomBtn.closest('.mermaid-container');
    if (!container) return;
    
    const mermaidPre = container.querySelector('pre.mermaid');
    if (!mermaidPre) return;
    
    // Get the original source from data attribute or text content
    const mermaidSource = mermaidPre.getAttribute('data-mermaid-source') || mermaidPre.textContent;
    
    if (mermaidSource) {
      openModal(mermaidSource);
    }
  });
})();
