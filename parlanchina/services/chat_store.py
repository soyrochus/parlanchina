import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from flask import current_app

from parlanchina.utils.markdown import render_markdown


def _data_dir() -> Path:
    data_dir: Path = current_app.config["DIRS"]["data"]
    session_dir = data_dir / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _history_path() -> Path:
    data_dir: Path = current_app.config["DIRS"]["data"]
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "history.jsonl"


def _session_path(session_id: str) -> Path:
    return _data_dir() / f"{session_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_history(role: str, text: str) -> None:
    entry = {"ts": _now(), "role": role, "text": text}
    history_file = _history_path()
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with history_file.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")


def list_sessions() -> list[dict[str, Any]]:
    """List sessions sorted by updated timestamp (desc)."""
    _data_dir().mkdir(parents=True, exist_ok=True)
    sessions: list[dict[str, Any]] = []
    for file in _data_dir().glob("*.json"):
        try:
            with file.open() as f:
                session = json.load(f)
                sessions.append(session)
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)


def load_session(session_id: str) -> Optional[dict[str, Any]]:
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        with path.open() as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def create_session(title: str | None, model: str) -> dict[str, Any]:
    session_id = uuid.uuid4().hex
    now = _now()
    session = {
        "id": session_id,
        "title": title or "New chat",
        "model": model,
        "mode": "ask",
        "enabled_internal_tools": None,
        "enabled_mcp_tools": None,
        "enabled_tools": None,  # legacy
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _save_session(session)
    return session


def append_user_message(session_id: str, content: str, *, model: str | None = None) -> dict:
    session = load_session(session_id)
    if not session:
        raise FileNotFoundError(f"Session {session_id} not found")
    session["messages"].append({"role": "user", "content": content})
    session["updated_at"] = _now()
    if model:
        session["model"] = model
    _save_session(session)
    _append_history("user", content)
    return session


def append_assistant_message(
    session_id: str,
    content: str,
    *,
    model: str | None = None,
    images: list[dict[str, str]] | None = None,
) -> dict:
    session = load_session(session_id)
    if not session:
        raise FileNotFoundError(f"Session {session_id} not found")
    html = render_markdown(content)
    message = {
        "role": "assistant",
        "raw_markdown": content,
        "html": html,
    }
    if images:
        message["images"] = images
    session["messages"].append(message)
    session["updated_at"] = _now()
    if model:
        session["model"] = model
    _save_session(session)
    _append_history("assistant", content)
    return message


def update_session_title(session_id: str, title: str) -> None:
    """Update the title of an existing session."""
    session = load_session(session_id)
    if not session:
        raise FileNotFoundError(f"Session {session_id} not found")
    session["title"] = title
    session["updated_at"] = _now()
    _save_session(session)


def delete_session(session_id: str) -> None:
    """Delete a session file."""
    path = _session_path(session_id)
    if not path.exists():
        raise FileNotFoundError(f"Session {session_id} not found")
    path.unlink()


def get_enabled_tools(session_id: str) -> list[str] | None:
    session = load_session(session_id)
    if not session:
        return None
    tools = session.get("enabled_tools")
    if isinstance(tools, list):
        return [t for t in tools if isinstance(t, str)]
    return None


def set_enabled_tools(session_id: str, enabled_tools: list[str]) -> None:
    session = load_session(session_id)
    if not session:
        raise FileNotFoundError(f"Session {session_id} not found")
    session["enabled_tools"] = enabled_tools
    session["updated_at"] = _now()
    _save_session(session)


def get_enabled_internal_tools(session_id: str) -> list[str] | None:
    session = load_session(session_id)
    if not session:
        return None
    tools = session.get("enabled_internal_tools")
    if tools is None:
        return None
    if isinstance(tools, list):
        return [t for t in tools if isinstance(t, str)]
    return None


def set_enabled_internal_tools(session_id: str, enabled_tools: list[str]) -> None:
    session = load_session(session_id)
    if not session:
        raise FileNotFoundError(f"Session {session_id} not found")
    session["enabled_internal_tools"] = enabled_tools
    session["updated_at"] = _now()
    _save_session(session)


def get_enabled_mcp_tools(session_id: str) -> list[str] | None:
    session = load_session(session_id)
    if not session:
        return None
    # Prefer new field, fall back to legacy enabled_tools
    tools = session.get("enabled_mcp_tools")
    if tools is None:
        tools = session.get("enabled_tools")
    if tools is None:
        return None
    if isinstance(tools, list):
        return [t for t in tools if isinstance(t, str)]
    return None


def set_enabled_mcp_tools(session_id: str, enabled_tools: list[str]) -> None:
    session = load_session(session_id)
    if not session:
        raise FileNotFoundError(f"Session {session_id} not found")
    session["enabled_mcp_tools"] = enabled_tools
    session["enabled_tools"] = enabled_tools  # keep legacy field in sync
    session["updated_at"] = _now()
    _save_session(session)


def get_mode(session_id: str) -> str:
    session = load_session(session_id)
    if not session:
        return "ask"
    mode = session.get("mode")
    if mode in {"ask", "agent"}:
        return mode
    return "ask"


def set_mode(session_id: str, mode: str) -> None:
    if mode not in {"ask", "agent"}:
        return
    session = load_session(session_id)
    if not session:
        raise FileNotFoundError(f"Session {session_id} not found")
    session["mode"] = mode
    session["updated_at"] = _now()
    _save_session(session)


def _save_session(session: dict[str, Any]) -> None:
    path = _session_path(session["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(session, f, indent=2)
