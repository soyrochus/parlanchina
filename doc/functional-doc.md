# Parlanchina – Functional Notes (provisional)

## Purpose and scope
- Single-user, local-first chat UI built with Flask + Jinja2. Runs in the browser, no hosted backend assumptions.
- Talks to OpenAI/Azure OpenAI via the Responses API with streaming; image generation uses the OpenAI image tool.
- Optimized for practical work sessions and demos: fast streaming, Markdown/Mermaid rendering, image support, MCP tools, and local persistence.

## Key capabilities (at a glance)
- Per-session model picker backed by `PARLANCHINA_MODELS`; defaults to `PARLANCHINA_DEFAULT_MODEL`.
- Ask vs Agent execution modes with per-session tool selection.
- Markdown-first rendering with Mermaid diagrams, zoom, and copy helpers.
- Image generation with progress overlays; images stored under `data/images/`.
- Session management (list, rename, delete, auto-title) with JSON storage in `data/sessions/`.
- Light/dark/system themes with Mermaid re-render to match theme.

## Primary user journeys
- **Launch and start**: open app; newest session loads or a new one is created. Model selector is pre-populated from env config.
- **Compose and send**: type in textarea; send via button or `Ctrl/Cmd+Enter`. Enter key otherwise behaves normally.
- **Streaming and rendering**: assistant replies stream as deltas; once complete, the saved raw Markdown renders in place. A copy button surfaces the raw assistant text per message.
- **Markdown and Mermaid**: GitHub-flavored Markdown rendered server-side; fenced ```mermaid blocks render with intelligent sizing, flicker-masking overlays, and zoom controls. Diagrams are automatically sized with type-specific constraints (ER diagrams: 800x500px+, state diagrams: 600x400px max, flowcharts: 700x400px+) while preserving aspect ratios.
- **Image generation**: in Agent/Ask modes, the model may call the internal image tool; UI shows generation overlays and labels. Generated images are intelligently sized (max 800x500px, min 200px width) with aspect ratio preservation. Images are stored in `data/images/` and referenced in transcripts for session reload.
- **Visual content zoom**: both Mermaid diagrams and generated images feature dedicated zoom controls that open content in modal overlays with enhanced sizing for detailed viewing.
- **Session handling**: sidebar lists conversations; rename/delete available from the menu. First user message prompts an automatic title suggestion. Sessions persist to JSON in `data/sessions/` and reload on launch.
- **Theme switching**: light/dark/system toggle; triggers Mermaid re-render to keep diagrams aligned with the theme.

## Modes, tools, and selection
- **Ask mode (default)**: single-shot reply. Only internal tools (e.g., `internal.image`) are considered; MCP tools are hidden.
- **Agent mode**: iterative loop (model ↔ tools) until the model finishes or limits are reached. Internal tools plus MCP tools are available.
- **Toolbox panel**: collapsible UI showing internal and MCP tools grouped by server. Users make a draft selection; Apply persists the selection for the current session, Cancel discards. The applied selection is reused for subsequent calls in that session.
- **Availability rules**: Ask mode counts only internal tools; Agent mode counts internal + MCP (if MCP is enabled). If MCP is unavailable (missing FastMCP or bad config), the panel reflects the disabled state.

## MCP integration
- Reads `mcp.json` on startup and spins up configured servers (stdio or SSE) through FastMCP. Default config includes a PostgreSQL MCP server.
- Tools are discovered per server; IDs use `server.tool` naming. Only tools from the applied selection are passed into chat calls.
- MCP failures are non-fatal: if `mcp.json` is missing/malformed or FastMCP is absent, MCP is disabled and the rest of the app works as usual.

## Configuration and runtime behavior
- Environment: `OPENAI_API_KEY`, `OPENAI_PROVIDER` (`openai`|`azure`), `OPENAI_API_BASE`, `OPENAI_API_VERSION`, `PARLANCHINA_MODELS`, `PARLANCHINA_DEFAULT_MODEL`.
- Logging: `LOG_LEVEL`, `LOG_FORMAT`, `LOG_TYPE` (`stream`|`file`), `LOG_FILE`. Defaults target console with timestamps.
- Startup ensures `data/sessions/` and `data/images/` exist. No authentication or multi-user support is present.
- API path: only the OpenAI/Azure Responses API is supported; legacy Chat Completions is out of scope.

## Data and persistence
- Sessions: stored as JSON per session under `data/sessions/`; include messages, model, mode, tool selection, and titles.
- Images: written to `data/images/` and referenced in session Markdown so they reload on revisit.
- Streaming: server streams newline-delimited JSON events; finalization step persists Markdown and any generated images.

## Visual content sizing and display
- **Intelligent Mermaid sizing**: diagrams are automatically sized based on type and content complexity:
  - ER diagrams: minimum 700px width, up to 1000px height for complex schemas
  - State diagrams: constrained to 600px max height to prevent excessive whitespace
  - Flowcharts: moderate 600-700px width with 400-700px height limits
  - Aspect ratio preservation prevents distortion while enforcing readability minimums
- **Smart image constraints**: generated images are sized for optimal viewing:
  - Maximum display size: 800x500px to prevent oversized content
  - Minimum readable size: 200px+ width for small images
  - Responsive behavior: scales appropriately on mobile (400x350px max)
  - Wrapper optimization: `fit-content` sizing prevents unnecessary container expansion
- **Enhanced zoom modals**: clicking zoom buttons opens content in overlays with:
  - Viewport-aware sizing (80% of screen or 1200px max for images)
  - Type-specific modal constraints for optimal detail viewing
  - Zoom slider controls for further magnification
  - Responsive modal behavior across screen sizes

## Non-functional notes and constraints
- Sanitization: server sanitizes Markdown before render; client uses DOMPurify during streaming preview.
- Error surfacing: tool/image errors appear inline in Markdown with concise explanations.
- Local-first: no cloud storage; user data stays under `data/`. Suitable for demos and personal workflows rather than shared environments.

## Pending/assumed
- FastMCP must be installed for MCP to work; otherwise tools are limited to internal ones.
- Only Responses API is supported today; other LLM providers or transports would require new adapters.
