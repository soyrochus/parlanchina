
You are an expert Python + Flask + Jinja2 developer and frontend engineer.

Create a **minimal but real chat application** named **“Parlanchina”** that talks to an OpenAI-compatible LLM (OpenAI or Azure OpenAI). This must be a clean, demo-ready, single-user web app with a correct architecture that can later grow into a multi-user system.

The FIRST IMPLEMENTATION MUST support:

1. **Streaming AI responses** (server-sent events or streamed chunk responses)
2. **Async execution** where required in Flask using `async def` routes or background streaming endpoints
3. **Markdown rendering** of assistant messages using a safe renderer (e.g. `markdown-it-py`, `marko`, or similar), including support for code blocks, inline code, lists, blockquotes, etc.

The rest of the requirements:

======================================================================
## Overall goals
- Stack: Python 3, Flask, Jinja2.
- Frontend: Tailwind CSS (CDN) following the layout of the provided `code.html` mockup. See [code.html](design/code.html) and [screen.png](design/screen.png)
- Scope: single-user, no auth, runs locally for development and demos.
- Persistence: chat sessions stored as JSON in `data/sessions/`, **behind a persistence façade**, so it can be swapped for a DB later.
- AI backend: OpenAI Chat Completions with support for **streamed responses**. Must accept both OpenAI and Azure OpenAI via `.env` using `python-dotenv`.
- Markdown: ALL assistant replies must be rendered in HTML via a Markdown renderer before being inserted into the template.
- Clean, extensible design.

======================================================================
## Project structure
Create:

- `parlanchina/`
  - `app.py` or `__init__.py` with app factory (`create_app()`), loading env, initializing Tailwind/static, etc.
  - `routes.py` (primary Flask views)
  - `services/`
    - `ai_client.py` — unified streaming wrapper around OpenAI/Azure clients.
    - `chat_store.py` — JSON-backed persistence façade.
  - `utils/markdown.py` — Markdown renderer returning safe HTML.
  - `templates/`
    - `base.html`
    - `chat.html`
  - `static/js/`
    - `theme.js`
    - `stream.js` — client-side streaming handler
  - `data/sessions/`
- `requirements.txt`
- `.env.example`
- `README.md`

======================================================================
## Environment variables

Load `.env` with python-dotenv. Use:

- `OPENAI_API_KEY`
- `OPENAI_PROVIDER` = `"openai"` (default) or `"azure"`
- `OPENAI_API_BASE` (Azure or custom endpoints)
- `OPENAI_API_VERSION` (for Azure)
- `PARLANCHINA_MODELS` — comma-separated list of allowed models
- `PARLANCHINA_DEFAULT_MODEL`

======================================================================
## AI client (streaming required!)

Implement `services/ai_client.py` with:

### Public interface
```python
async def stream_chat_completion(messages: list[dict], model: str):
    """
    Async generator that yields streamed chunks of assistant text.
    """
````

### Behavior

* If provider = openai:

  * Use OpenAI Python SDK with `stream=True`
  * Yield `delta` chunks as they arrive
* If provider = azure:

  * Use Azure OpenAI ChatCompletions with `stream=True`
  * Yield delta chunks

### Failure handling

* On network/API errors, yield a “system-style” error message in streaming mode.
* Logging of model, timing, token counts.


Here is a **clean, minimal, self-contained Markdown specification section** that defines *only* the Markdown rendering requirements **assuming streaming**.
No architecture, no additional context, just the Markdown-related contract.

---

# **Markdown Rendering Specification (Streaming-Aware)**

## 1. Input Format

* The assistant’s response arrives **as streamed text chunks** from the LLM.
* Each chunk is appended to a **raw Markdown buffer** on the client side.
* The complete final assistant message is stored **as raw Markdown**.

## 2. Rendering Requirements

* Markdown must be rendered **into safe HTML** before being displayed.
* Rendering must occur:

  1. **Incrementally during streaming** (approximate/partial rendering).
  2. **Once again after stream completion** (final, correct rendering).

## 3. Supported Markdown Features

The renderer must support at minimum:

* Paragraphs and line breaks
* Bold, italic, underline
* Inline code
* Fenced code blocks (`…`)
* Syntax highlighting (optional, but allowed)
* Ordered and unordered lists
* Blockquotes
* Headings (H1–H6)
* Links
* Tables (optional but recommended)

## 4. Security

* The Markdown-to-HTML pipeline must:

  * **Escape or remove unsafe HTML tags**
  * Strip embedded scripts, iframes, and inline event handlers
  * Sanitize code blocks

## 5. Client-Side Rendering During Streaming

* As text streams in, the frontend:

  * Updates the visible assistant bubble with **intermediate HTML** rendered from the current Markdown buffer.
  * This is approximate; formatting may flicker during partial rendering.
* When the final chunk arrives:

  * The raw Markdown buffer is passed through the renderer **one final time**.
  * The bubble is replaced with the **final, correct HTML**.

## 6. Backend Rendering (Canonical)

* The backend must also provide a Markdown-to-HTML function.
* After streaming finishes, the fully assembled Markdown string is:

  * Passed to the backend renderer
  * Sanitized and stored as the authoritative rendered HTML version (used for page reloads)

## 7. Storage Format

Each assistant message must store:

* `raw_markdown`: the unmodified Markdown string
* `html`: sanitized HTML produced by the backend renderer

## 8. Rendering Consistency

* The frontend renderer (for streaming preview) and backend renderer (canonical) must follow **similar rules** to avoid rendering discrepancies.
* Minor differences are acceptable during live streaming.

## 9. Mermaid Support

The Markdown renderer must detect fenced code blocks beginning with ```mermaid and render them as Mermaid diagrams.

During streaming, Mermaid blocks may arrive partially; they must be treated as plain text until the full fenced block is complete.

After stream completion, the final rendered HTML must pass Mermaid diagrams to the Mermaid JS runtime (on the client) for rendering.

Mermaid rendering must run after the final Markdown-to-HTML conversion step (post-stream).

Unsafe HTML or script injection inside Mermaid blocks must be sanitized before rendering.

======================================================================

## Chat storage façade

`services/chat_store.py` must provide:

```python
def list_sessions() -> list
def load_session(session_id: str) -> dict
def create_session(title: str | None, model: str) -> dict
def append_user_message(session_id: str, content: str)
def append_assistant_message(session_id: str, content: str)
```

Back all operations with JSON files in `data/sessions/SESSION_ID.json`.

======================================================================

## Markdown rendering

Implement `utils/markdown.py`:

* Use `markdown-it-py` or `marko`.
* Enable:

  * fenced code blocks
  * inline code
  * headings
  * lists
  * blockquotes
* Sanitize output (strip dangerous tags).
* Provide:

```python
def render_markdown(md_text: str) -> str:
    """Return safe HTML from markdown."""
```

All assistant messages must be stored as *raw markdown* but rendered to HTML in templates.

======================================================================

## Flask routes (async where needed)

### `GET /`

Redirect to the newest session or create a new one.

### `POST /new`

Create a new session; redirect to `/chat/<id>`.

### `GET /chat/<id>`

Render the chat UI.

### `POST /chat/<id>`

Handle user message submission:

* Append user message to JSON
* Initiate streaming response
* Route must trigger streaming endpoint

### `GET /chat/<id>/stream`

Returns a **streaming response** (SSE or chunked response). The frontend JS listens to this endpoint.

======================================================================

## Streaming protocol (client side)

Create `static/js/stream.js`:

* On form submit:

  * Print user message immediately into UI
  * Start fetching `/chat/<id>/stream?model=...`
  * Append streamed text chunks as they arrive to an “assistant message bubble”
  * When streaming finishes:

    * Send final assembled assistant message to the backend via AJAX (`POST /chat/<id>/finalize`) OR include content in the stream endpoint’s final event
    * Replace temporary bubble with final rendered markdown bubble

Keep the code small and clean.

======================================================================

## Templates (Jinja2)

Use Tailwind as in the screenshot and `code.html` design.

### Left sidebar

* Theme toggle (Light/Dark/System)
* “New chat” button
* List of sessions

### Center content

* Model selector dropped in top-right
* Messages list, markdown-rendered assistant messages, user messages right-aligned
* Streaming output: placeholder bubble updated in real time

### Bottom input box

* Textarea
* Send button
* Three placeholder popover options (no functionality yet)

======================================================================

## Theme support (front-end only)

Implement standard 3-mode theme toggle:

* Light
* Dark
* System

Store preference in `localStorage`. Use Tailwind dark mode class toggling.

======================================================================

## Non-functional

* Clean code, docstrings, comments.
* Clear README with instructions to run:

  * `python3 -m venv`
  * `pip install -r requirements.txt`
  * Copy `.env.example` → `.env`
  * `flask run`

======================================================================

Deliverable: a fully working Flask/Jinja2 project with:

* async streaming AI responses,
* markdown rendering,
* Tailwind UI based on the mockup,
* simple local JSON persistence,
* multi-model selector,
* theme toggle,
* ready to extend into a multi-user system.


