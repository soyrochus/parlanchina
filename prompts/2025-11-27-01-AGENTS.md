You are an expert Python + Flask engineer.

Refactor the existing Parlanchina app so that **all LLM calls** use the **OpenAI Responses API** instead of the Chat Completions API.

⚠️ IMPORTANT
- Do NOT change the external behavior for the user.
- Do NOT add image generation yet.
- Streaming, Markdown, Mermaid, file upload, chat history, model selector, etc. must keep working as they do now.
- This change is purely about the backend LLM call path.

=====================================
1. Scope of the refactor
=====================================

Currently the app uses the Chat Completions API (or similar) to:
- send the chat history,
- stream back the assistant’s textual response,
- append the final text to the chat history as Markdown.

Replace that with the **Responses API**, preserving:

- Same system / user / assistant roles and content semantics.
- Same streaming UX (incremental text in the UI).
- Same message storage model (raw Markdown in history).

Do NOT touch:
- MCP integration,
- storage abstraction,
- UI templates (except where strictly necessary to adapt to internal changes).

=====================================
2. New LLM client interface
=====================================

Introduce or adapt a small **LLM service** module, e.g. `services/llm.py`, with a **single public entry point** that the rest of the app uses:

- `stream_response(messages: list[dict], model: str)`  

Requirements:

- `messages` is the same structure the app already uses:
  - list of `{ "role": "system"|"user"|"assistant", "content": "<markdown text>" }`.
- The function must:
  - Call the **OpenAI Responses API** with:
    - `model` = the selected chat model.
    - `input` = the conversation (converted to the format the Responses API expects).
    - **No tools** yet.
  - Return an **async or generator-style stream of text chunks** representing the assistant’s reply, in order.
- The caller (Flask route) must be able to iterate over this stream and send chunks to the frontend as it does today.

You can change internal plumbing, but the Flask routes should ideally only need minor adjustments to call this new function instead of the old completions client.

=====================================
3. Responses API specifics
=====================================

Implement the new LLM call path with the OpenAI Responses API:

- Use the official Python client’s Responses interface.
- Convert the existing chat `messages` list into the `input` format expected by the Responses API (e.g. a sequence of role-tagged messages).
- Enable **streaming** in the Responses call and map the streamed deltas into simple text chunks for the UI.

Constraints:

- Only text output is required in this phase.
- Ignore tools and images for now.
- Any metadata the Responses API returns that is not needed for streaming + final text can be discarded.

=====================================
4. Integration with Flask streaming
=====================================

Adapt the existing Flask route(s) that handle chat completion so that:

- They now call `stream_response(messages, model)` instead of the previous chat-completions helper.
- They continue to:
  - append the user message to history,
  - stream the assistant chunks to the client,
  - on completion, store the final assistant message in history as a single Markdown string.

The HTTP streaming mechanism (e.g. `yield`ing chunks in a Flask response) should remain the same from the client’s point of view.

=====================================
5. Error handling and logging
=====================================

- Preserve existing error behavior where possible:
  - If the LLM call fails, send a short error message back to the user as an assistant message.
- Add minimal logging indicating:
  - the model used,
  - whether the Responses API call succeeded or failed.

=====================================
6. Backwards compatibility
=====================================

- The existing `.env` configuration for models and API keys must continue to work, just reused for Responses.
- The model selector UI must keep working; it should map 1:1 to the `model` parameter passed to the Responses API.

Deliver a clean, minimal refactor where:
- Only the LLM client layer is changed to use Responses,
- Chat behavior for the user remains identical,
- The code is ready for a second phase where we will add tools/image_generation on top of the Responses API.
