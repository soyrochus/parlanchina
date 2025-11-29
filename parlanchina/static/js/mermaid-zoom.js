(() => {
  const modal = document.getElementById('mermaid-modal');
  const modalBody = document.getElementById('mermaid-modal-body');
  const closeBtn = document.getElementById('mermaid-modal-close');
  const zoomSlider = document.getElementById('mermaid-zoom-slider');
  const zoomValue = document.getElementById('mermaid-zoom-value');
  
  let currentDiagramContainer = null;
  let currentType = 'mermaid'; // mermaid | image
  let currentImage = null;
  
  const openModal = async ({ type, mermaidSource, imageSrc, imageAlt }) => {
    // Clear previous content
    modalBody.innerHTML = '';
    
    currentDiagramContainer = null;
    currentImage = null;
    currentType = type;

    // Create a container for zoomable content
    const container = document.createElement('div');
    container.className = 'mermaid-diagram-container';
    container.style.transformOrigin = 'center center';
    container.style.transition = 'transform 0.2s ease';

    if (type === 'mermaid') {
      const pre = document.createElement('pre');
      pre.className = 'mermaid';
      pre.textContent = mermaidSource || '';
      container.appendChild(pre);
      modalBody.appendChild(container);
      currentDiagramContainer = container;
    } else if (type === 'image') {
      const img = document.createElement('img');
      img.src = imageSrc || '';
      if (imageAlt) img.alt = imageAlt;
      img.style.maxWidth = '100%';
      img.style.height = 'auto';
      container.appendChild(img);
      modalBody.appendChild(container);
      currentDiagramContainer = container;
      currentImage = img;
    }

    // Reset zoom slider
    zoomSlider.value = 100;
    zoomValue.textContent = '100%';
    container.style.transform = 'scale(1)';
    
    // Show modal
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    
    // Render the mermaid diagram
    if (type === 'mermaid' && window.mermaid) {
      const pre = container.querySelector('pre.mermaid');
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
    const mermaidBtn = e.target.closest('.mermaid-zoom-btn');
    const imageBtn = e.target.closest('.image-zoom-btn');
    if (!mermaidBtn && !imageBtn) return;
    
    e.preventDefault();
    e.stopPropagation();

    if (mermaidBtn) {
      const container = mermaidBtn.closest('.mermaid-container');
      if (!container) return;
      const mermaidPre = container.querySelector('pre.mermaid');
      if (!mermaidPre) return;
      const mermaidSource = mermaidPre.getAttribute('data-mermaid-source') || mermaidPre.textContent;
      if (mermaidSource) {
        openModal({ type: 'mermaid', mermaidSource });
      }
      return;
    }

    if (imageBtn) {
      const wrapper = imageBtn.closest('.generated-image-wrapper');
      if (!wrapper) return;
      const img = wrapper.querySelector('img');
      if (!img) return;
      openModal({ type: 'image', imageSrc: img.src, imageAlt: img.alt });
    }
  });
})();
