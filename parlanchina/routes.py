import asyncio
import json
import logging
import threading

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from parlanchina.services import chat_store, image_store, internal_tools, llm, mcp_manager

bp = Blueprint("main", __name__)
logger = logging.getLogger(__name__)


@bp.get("/")
def index():
    """Redirect to the latest session or create a new one."""
    sessions = chat_store.list_sessions()
    if sessions:
        return redirect(url_for("main.chat", session_id=sessions[0]["id"]))

    model = _resolve_model()
    session = chat_store.create_session("New chat", model)
    return redirect(url_for("main.chat", session_id=session["id"]))


@bp.post("/new")
def new_chat():
    model = request.form.get("model") or _resolve_model()
    title = request.form.get("title") or "New chat"
    session = chat_store.create_session(title, model)
    return redirect(url_for("main.chat", session_id=session["id"]))


@bp.get("/chat/<session_id>")
def chat(session_id: str):
    session = chat_store.load_session(session_id)
    if not session:
        abort(404)

    models = current_app.config.get("PARLANCHINA_MODELS", [])
    selected_model = session.get("model") or _resolve_model()
    sessions = chat_store.list_sessions()

    return render_template(
        "chat.html",
        session=session,
        sessions=sessions,
        models=models,
        selected_model=selected_model,
    )


@bp.post("/chat/<session_id>")
def post_message(session_id: str):
    data = request.get_json(silent=True) or request.form
    content = (data.get("message") or "").strip()
    model = data.get("model") or None
    if not content:
        abort(400, "Message content required")

    session = chat_store.load_session(session_id)
    if not session:
        abort(404)

    # Check if this is the first user message in the session
    is_first_message = len(session.get("messages", [])) == 0
    
    chat_store.append_user_message(session_id, content, model=model)
    
    # Generate session title in background for first message
    if is_first_message:
        used_model = model or session.get("model") or _resolve_model()
        _generate_session_title_async(session_id, content, used_model)
    
    return jsonify({"status": "ok"})


@bp.get("/chat/<session_id>/stream")
def stream_response(session_id: str):
    session = chat_store.load_session(session_id)
    if not session:
        abort(404)

    model = request.args.get("model") or session.get("model") or _resolve_model()
    payload_messages = _format_messages_for_model(session)
    app = current_app._get_current_object()
    mode = chat_store.get_mode(session_id)

    # Internal tools default: all
    internal_enabled = chat_store.get_enabled_internal_tools(session_id)
    if internal_enabled is None:
        internal_enabled = internal_tools.all_tool_ids()
        chat_store.set_enabled_internal_tools(session_id, internal_enabled)

    # MCP tools only when in agent mode and MCP is available
    mcp_enabled_tools: list[str] = []
    if mode == "agent" and mcp_manager.is_enabled():
        enabled_tools = chat_store.get_enabled_mcp_tools(session_id)
        if enabled_tools is None:
            try:
                enabled_tools = [tool["id"] for tool in mcp_manager.list_all_tools()]
                chat_store.set_enabled_mcp_tools(session_id, enabled_tools)
            except Exception:
                enabled_tools = []
        mcp_enabled_tools = enabled_tools or []

    def generate():
        import asyncio
        with app.app_context():
            text_buffer = ""
            images: list[dict[str, str]] = []
            # Get or create event loop for this thread
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Run the async generator in sync context
            async_gen = llm.stream_response(
                payload_messages,
                model,
                mode=mode,
                internal_tools=internal_enabled,
                mcp_tools=mcp_enabled_tools,
            )
            while True:
                try:
                    event = loop.run_until_complete(async_gen.__anext__())
                    if event.type == "text_delta":
                        delta = event.text or ""
                        if delta:
                            text_buffer += delta
                            yield json.dumps({"type": "text_delta", "text": delta}) + "\n"
                    elif event.type == "image_start":
                        yield json.dumps({"type": "image_start"}) + "\n"
                    elif event.type == "image_call":
                        if not event.image_b64:
                            continue
                        try:
                            meta = image_store.save_image_from_base64(event.image_b64)
                            alt_text = _derive_alt_text(event.image_params)
                            image_payload = {"url": meta.url_path, "alt_text": alt_text}
                            images.append(image_payload)
                            addition = f"\n\n![{alt_text}]({meta.url_path})\n"
                            text_buffer += addition
                            yield (
                                json.dumps(
                                    {
                                        "type": "image",
                                        "url": meta.url_path,
                                        "alt_text": alt_text,
                                        "markdown": addition,
                                    }
                                )
                                + "\n"
                            )
                        except Exception as exc:  # pragma: no cover - safety
                            logger.exception("Failed to persist generated image: %s", exc)
                            yield json.dumps({"type": "error", "message": "Image save failed"}) + "\n"
                    elif event.type == "error":
                        error_message = event.text or "LLM error"
                        analysis = ""
                        try:
                            analysis_prompt = [
                                {
                                    "role": "system",
                                    "content": "You are a helpful assistant that explains model or tool errors succinctly for end users. Provide a brief, calm summary and a likely cause/next step.",
                                },
                                {
                                    "role": "user",
                                    "content": f"Explain this image-generation error for the user in 2-3 sentences:\n\n{error_message}",
                                },
                            ]
                            analysis = loop.run_until_complete(
                                llm.complete_response(analysis_prompt, model)
                            )
                        except Exception as exc:  # pragma: no cover
                            logger.exception("Failed to analyze error via LLM: %s", exc)
                            analysis = ""

                        markdown_error = (
                            "\n\n**Image generation failed**\n\n"
                            f"```\n{error_message}\n```\n"
                        )
                        if analysis:
                            markdown_error += f"\n{analysis}\n"
                        text_buffer += markdown_error
                        yield (
                            json.dumps(
                                {
                                    "type": "error",
                                    "message": error_message,
                                    "analysis": analysis,
                                    "markdown": markdown_error,
                                }
                            )
                            + "\n"
                        )
                    elif event.type == "text_done":
                        if event.text:
                            if not text_buffer or len(event.text) > len(text_buffer):
                                text_buffer = event.text
                except StopAsyncIteration:
                    break
            yield json.dumps({"type": "text_done", "text": text_buffer, "images": images}) + "\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(generate(), mimetype="text/plain", headers=headers)


@bp.post("/chat/<session_id>/rename")
def rename_session(session_id: str):
    """Rename a session."""
    data = request.get_json(force=True)
    new_title = (data.get("title") or "").strip()
    if not new_title:
        abort(400, "Title is required")
    
    try:
        chat_store.update_session_title(session_id, new_title)
        return jsonify({"status": "ok", "title": new_title})
    except FileNotFoundError:
        abort(404)


@bp.delete("/chat/<session_id>")
def delete_session(session_id: str):
    """Delete a session."""
    try:
        chat_store.delete_session(session_id)
        return jsonify({"status": "ok"})
    except FileNotFoundError:
        abort(404)


@bp.get("/chat/<session_id>/info")
def get_session_info(session_id: str):
    """Get session information including current title."""
    session = chat_store.load_session(session_id)
    if not session:
        abort(404)
    return jsonify({
        "id": session["id"],
        "title": session["title"],
        "updated_at": session["updated_at"]
    })


@bp.post("/chat/<session_id>/finalize")
def finalize_message(session_id: str):
    data = request.get_json(force=True)
    content = data.get("content", "")
    model = data.get("model") or None
    images = data.get("images") or []
    session = chat_store.load_session(session_id)
    if not session:
        abort(404)
    message = chat_store.append_assistant_message(
        session_id, content, model=model, images=images
    )
    return jsonify({"status": "ok", "html": message["html"], "raw": message["raw_markdown"]})


@bp.get("/images/<path:filename>")
def serve_image(filename: str):
    return image_store.serve_image(filename)


def _resolve_model() -> str:
    models = current_app.config.get("PARLANCHINA_MODELS") or []
    default_model = current_app.config.get("PARLANCHINA_DEFAULT_MODEL") or ""
    if default_model:
        return default_model
    if models:
        return models[0]
    return ""


def _format_messages_for_model(session: dict) -> list[dict]:
    formatted = []
    for message in session.get("messages", []):
        if message["role"] == "assistant":
            content = message.get("raw_markdown") or message.get("content") or ""
        else:
            content = message.get("content") or ""
        formatted.append({"role": message["role"], "content": content})
    return formatted


def _derive_alt_text(params: dict | None) -> str:
    if not params:
        return "Generated image"
    for key in ("alt_text", "description", "prompt"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Generated image"


def _generate_session_title_async(session_id: str, user_message: str, model: str):
    """Generate a session title in a background thread."""
    # Capture the current Flask app context
    app = current_app._get_current_object()
    
    def _run_title_generation():
        try:
            # Use the captured app context in the thread
            with app.app_context():
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Prepare the title generation prompt
                title_prompt = [
                    {
                        "role": "system", 
                        "content": "You are a helpful assistant that creates concise, descriptive titles for chat sessions. Generate a short title (3-6 words) that summarizes the main topic or request from the user's message. Respond with only the title, no quotes or additional text."
                    },
                    {
                        "role": "user", 
                        "content": f"Create a short title for a chat session based on this user message: {user_message}"
                    }
                ]
                
                # Generate title using AI
                title = loop.run_until_complete(
                    llm.complete_response(title_prompt, model)
                )
                
                # Clean up the title (remove quotes if present, limit length)
                title = title.strip().strip('"').strip("'")
                if len(title) > 50:  # Limit title length
                    title = title[:47] + "..."
                
                # Update the session with the new title
                chat_store.update_session_title(session_id, title)
                logger.info(f"Generated title for session {session_id}: {title}")
                
        except Exception as e:
            logger.error(f"Failed to generate title for session {session_id}: {e}")
        finally:
            if 'loop' in locals():
                loop.close()
    
    # Run in background thread
    thread = threading.Thread(target=_run_title_generation, daemon=True)
    thread.start()
