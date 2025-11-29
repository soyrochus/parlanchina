# ✅ **FULL IMPLEMENTATION PROMPT — PARLANCHINA IMAGE GENERATION **

You are extending **Parlanchina**, a real AI chat application built with **Flask + Jinja2 + Python**.
Repository: [https://github.com/soyrochus/parlanchina](https://github.com/soyrochus/parlanchina)

Parlanchina is **not just a demo toy** — it is a **demo-performing application** used in client sessions.
It must remain stable, comprehensible, maintainable, and extensible.

Currently, Parlanchina supports:

* **Streaming text generation** (OpenAI Responses API)
* **Markdown rendering**
* **Mermaid diagrams** with a “rendering overlay” that hides flickers
* **Session storage JSON files** (`chat_store.py` → `data/sessions/`)
* **File uploads**
* **A well-structured frontend with message-level UI state**

Your task is to implement **image generation** using the **OpenAI Responses API** + the built-in **`image_generation` tool**.

No second LLM call.
No special `/image` endpoint.
The model decides when to generate images.

---

# 1. 🎯 **High-Level Goal**

Extend Parlanchina so that **a single Responses call per assistant message** can produce:

* Only text
* Only images
* Text + images together

Images must:

* Be stored under `data/images/` using a new image storage abstraction
* Be rendered in the UI with placeholders + overlay while they are being prepared
* Be included in chat history as Markdown image tags (`![alt](url)`)
* Appear correctly after refresh (session replay)

All existing text behavior must remain *completely unchanged*.

---

# 2. 🧠 **LLM Integration (llm.py)**

Modify `llm.py` so that:

### 2.1. The single streaming function becomes tool-aware:

```python
async def stream_response(
    messages: list[dict],
    model: str,
    enable_image_tool: bool = True,
) -> AsyncIterator[LLMEvent]
```

### 2.2. Define an internal event structure (you decide class/dict):

* `type`: `"text_delta" | "text_done" | "image_call" | "error"`
* `text`: optional string
* `image_b64`: optional base64 string
* `image_params`: optional metadata (size, format, etc.)
* `raw_event`: underlying Responses API payload (optional)

### 2.3. The Responses call MUST include the tool:

```
tools = [{
  "type": "image_generation",
  "model": "gpt-image-1",
  "size": "1024x1024",
  "quality": "high",
  "output_format": "png"
}]
```

### 2.4. Event mapping:

* Normal streamed deltas → `LLMEvent(type="text_delta")`
* Final assistant text → `LLMEvent(type="text_done")`
* Tool call result → `LLMEvent(type="image_call", image_b64=...)`

NOTE:
We ignore partial_image events in v1; handle only the final base64 image.

---

# 3. 🗂️ **Image Storage Abstraction (`image_store.py`)**

Create a new module:

```
parlanchina/services/image_store.py
```

### 3.1. Directory

* Images must be stored under:

```
data/images/
```

Separate from session storage.

### 3.2. API

Create:

```python
class ImageMeta:
    id: str
    filename: str
    url_path: str
    created_at: str
```

Expose:

```python
def save_image_from_base64(image_b64: str, ext="png") -> ImageMeta
def get_image_url(meta: ImageMeta) -> str
```

### 3.3. Serving images

Implement **one** of:

* A Flask route:

```
/images/<filename>
```

returning `send_from_directory("data/images", filename)`

OR

* Save to `/static/generated/` and serve as static files.

Leave room for future DB/storage backend.

---

# 4. 💾 **Session Storage (`chat_store.py`)**

Extend message schema:

Add:

```json
"images": [
  {
    "url": "/images/<id>.png",
    "alt_text": "text description"
  }
]
```

Where:

* `alt_text` is usually a short description (model-generated or derived from message content).
* `images` is optional and empty on text-only messages.

**Do NOT store base64 in session files.**

---

# 5. 🔄 **Routing Layer (`routes.py`)**

Modify `/chat/<session_id>/stream` so that:

* It iterates over `LLMEvent`s.
* On `text_delta` → stream text to client (no change).
* On `image_call`:

  1. Save image to disk using `image_store.save_image_from_base64`.
  2. Create a temporary **streaming message** for the frontend:

     * Something like a structured `"image_start"` event OR
     * A Markdown image string `![alt](url)`
  3. Prepend a placeholder overlay for the UI.
* On `text_done` → send final consolidated text.

Modify `/chat/<session_id>/finalize`:

* Must append the assistant message including:

  * Final Markdown text
  * Any `images` references

---

# 6. 🎨 **Frontend Rendering**

Reuse the existing **Mermaid rendering overlay pattern**.

### 6.1. New message state flags:

For each assistant message, track:

* `isRenderingImage: boolean`
* `imageUrls: []` (list of URLs)
* (If needed) `imagePendingCount`

### 6.2. Overlay behavior (same as Mermaid)

* When the stream signals an image is being generated:

  * Create a visible placeholder box with fixed height.
  * Render an opaque rounded overlay (“rendering…” shimmer).
  * Once actual image URL arrives, hide overlay and show `<img>`.

### 6.3. Markdown integration

* Final assistant message must contain Markdown:

```
![alt text](/images/<id>.png)
```

* Rendering pipeline already converts this to `<img>`.

---

# 7. 🧭 **Model Behavior (implicit)**

In the **system prompt**, code agent should instruct the model:

* Use normal text unless an image is clearly beneficial.
* If an image is useful or requested, call `image_generation` at least once.
* Always accompany generated images with a short descriptive text.

---

# 8. ✔️ **Non-Negotiable Constraints**

* **Text streaming must not change.**
* **Mermaid rendering must not change.**
* **Do not break current chat history semantics.**
* **Do not store binary data in chat sessions.**
* **Do not create a second OpenAI call per turn.**
* **Keep the implementation clear, predictable, and modular.**

---

# 9. 📌 **Deliverables expected from the coding agent**

The agent must:

1. Modify `llm.py` to support mixed text+image events via Responses tool calls.
2. Create `image_store.py` with the abstraction described.
3. Extend streaming logic in `routes.py` to handle images.
4. Extend `chat_store.py` message schema to record image metadata.
5. Extend templates + JS so image overlays behave like Mermaid overlays.
6. Ensure final Markdown includes images correctly.
7. Ensure all functionality remains stable across refresh and session replay.

