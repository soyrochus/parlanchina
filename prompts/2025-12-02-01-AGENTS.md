You are a coding agent working on the Parlanchina project (a local Flask-based ChatGPT-like app). Your task is to implement a **new “view source” popup button** for each assistant reply in the chat UI.

There is already:
- A **copy-to-clipboard button** per reply that copies the plain text of that reply.
- A **zoom popup mechanism** used for images and Mermaid diagrams (triggered by some zoom control, implemented with HTML + JS in the frontend).

Your new feature
Add, for each assistant reply, a **small button next to the copy button** that opens a **modal popup** which:
- Renders the **full content of that reply** as **markdown**, including:
  - Headings
  - Lists
  - Code blocks with syntax highlighting
- Is **read-only** (no editing)
- Is **scrollable** if the content is long
- Uses the **same popup / overlay mechanism** as the current image / Mermaid zoom (no new modal framework)
- Shows the content in a **fixed-width, code-friendly style** so code is clearly readable

High-level behavior
1. For every assistant message rendered in `chat.html`, there should be:
   - The existing copy-to-clipboard button (unchanged).
   - A new “view source” button to its left or right (small icon; exact icon is up to you, but something like `</>` or a magnifier on paper is fine).
2. Clicking this new button:
   - Opens a popup overlay using the **same modal structure and JS logic** as the current zoom popup (do not invent a new modal pattern).
   - The popup title can be something like “View message source” or “Rendered source”.
   - The body of the popup shows the **rendered markdown** for that reply, including syntax-highlighted code.
3. The popup must:
   - Be read-only
   - Allow vertical scrolling when content is taller than the viewport
   - Use existing CSS as much as possible (reuse classes / styles used by the zoom popup and code blocks).

Technical guidance

Frontend (HTML / JS)
- In `templates/chat.html`:
  - Locate the loop that renders each message in the conversation, including the existing copy-to-clipboard button and any metadata.
  - For each **assistant reply**, add:
    - A new button element with:
      - A distinct CSS class, e.g. `view-source-btn`.
      - A data attribute that uniquely identifies the message whose content must be shown, e.g. `data-message-id="{{ message.id }}"`, or `data-index="{{ loop.index0 }}"`, depending on what is already available.
      - A small text/icon label like `</>` or `SRC`.
  - Ensure the raw content for each message (before HTML escaping) is available to the frontend in some way so the popup can reconstruct the full markdown. You can:
    - Embed the raw markdown in a hidden `<script type="application/json" ...>` block attached to the message container, or
    - Use a `data-raw` attribute if safe and not too large, or
    - Re-use whatever mechanism is already used by the copy-to-clipboard button, if that already has access to the raw message content.

- In `static/js/stream.js`:
  - Find the existing event delegation / listeners for:
    - Copy-to-clipboard button
    - Zoom / Mermaid popup (if present here)
  - Add a new click handler for the `.view-source-btn`:
    - Identify the associated message container and retrieve the raw markdown content.
    - Pass that content to a function that opens the popup in “markdown view” mode.
  - If the zoom popup is controlled from another JS file (e.g. `mermaid-zoom.js`), expose or reuse a function to open the same modal with arbitrary HTML content, e.g.:
    - `openModalWithContent(html)` or similar.
    - If such a function does not exist, refactor the existing zoom logic so that:
      - The modal opening, closing, and overlay behavior is in one reusable function.
      - The zoomed image/Mermaid diagram is just one caller of that function.
      - The new “view source” logic is another caller, providing a different HTML body.
  - For the markdown rendering, you have two options:
    1) If the **frontend already uses a JS markdown renderer** (e.g. marked.js) or a syntax highlighter (e.g. highlight.js), reuse that:
       - Convert raw markdown to HTML on the client.
       - Insert it into the modal content element.
       - Run syntax highlighting if needed (e.g. `hljs.highlightAll()`).
    2) If markdown is rendered **server-side** already (e.g. `utils/markdown.py`), and the HTML is available in the message container:
       - You may inject the already-rendered HTML into the modal.
       - Ensure it is not double-escaped.
  - Make the modal content container scrollable via CSS:
    - Set a max-height (e.g. `70vh`) and `overflow-y: auto` on the body area of the modal.

Existing modal reuse
- Look at how the image / Mermaid zoom popup works:
  - Identify:
    - The modal HTML structure in the templates (probably in `base.html` or `chat.html`).
    - The JS that:
      - Opens the modal,
      - Injects content (zoomed image/Mermaid),
      - Closes the modal on overlay click/close button.
  - Do not change its behavior for images/Mermaid.
  - Extend that mechanism with a **new “mode”** or simply a new callsite that:
    - Uses the same modal, but injects a scrollable `<div>` with rendered markdown/code instead of an image.
- Keep a single modal in the DOM; do not create multiple overlays.

Styling
- Use existing CSS classes if present for:
  - Code blocks, e.g. `.code-block`, `pre code`, etc.
  - Modal content and header.
- If necessary, add minimal new CSS to:
  - Make the modal body scrollable.
  - Slightly adjust font to a monospace for code sections, while leaving markdown text as normal.
- Do not introduce heavy new styling frameworks.

Backend
- Do not change backend logic unless necessary to expose the **raw message text** to the frontend.
- If the frontend currently only sees HTML (after markdown rendering), and the copy-to-clipboard logic already has access to the raw text, reuse that same source.
- If needed, extend the message serialization in `routes.py` to include `raw_text` and pass that through to the template.

Acceptance criteria
1. For each assistant reply in the chat:
   - A new “view source” button appears next to the copy-to-clipboard button.
2. Clicking the “view source” button:
   - Opens the existing modal overlay.
   - Shows the **full message content** rendered as markdown, including syntax-highlighted code blocks.
   - The content is read-only and scrollable.
3. Closing the modal returns to the normal chat view without affecting the rest of the UI.
4. On both Mac and Linux (desktop browser), the behavior is consistent.
5. Existing image / Mermaid zoom still works exactly as before.

Implementation requirements
- Do not rename or move existing files or directories.
- Keep the implementation localized to:
  - `templates/chat.html`
  - `static/js/stream.js`
  - Reuse `mermaid-zoom.js` / modal-related JS as needed.
  - Minor CSS additions if strictly necessary.
- Keep code clean, commented where non-obvious, and consistent with current coding style in the repo.

