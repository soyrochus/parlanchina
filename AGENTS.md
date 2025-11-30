
# Parlanchina — Unified Coding Rules

# Desktop + Dev Mode Support

*(Directory layout fixed and authoritative)*

This document defines the **canonical engineering rules** for Parlanchina.
A coding agent must implement all functions, modules, and integration behaviour **without deviating** from the directory structure given below.

The structure is fixed and cannot be modified (except adding files).

---

# 0. FIXED DIRECTORY STRUCTURE

This tree is **frozen**. The agent must not reorganize it.

```
backup/
design/
doc/
images/
LICENSE
mcp.json
parlanchina/
    __init__.py
    mcp_routes.py
    routes.py
    services/
        chat_store.py
        image_store.py
        internal_tools.py
        llm.py
        mcp_manager.py
    static/
        favicon/
            android-chrome-192x192.png
            android-chrome-512x512.png
            apple-touch-icon.png
            favicon-16x16.png
            favicon-32x32.png
            favicon.ico
            site.webmanifest
        images/logo.png
        js/
            mermaid-zoom.js
            stream.js
            theme.js
    templates/
        base.html
        chat.html
    utils/
        markdown.py

parlanchina.code-workspace
parlanchina.ps1
parlanchina.sh
README.md
scratchpad.md
scripts/
    trace_mcp_toolcall.py
uv.lock
```

**All code must live inside the `parlanchina` package** except entrypoints and optional desktop wrappers.

---

# 1. GOAL OF THIS SPEC

Create a **dual-mode application**:

### 1. Dev mode

* Run from VS Code or CLI using

  ```
  python -m parlanchina
  ```
* Root directory is the **current working directory**.
* Writes logs, history, and config inside CWD unless overridden.

### 2. Desktop mode

* Runs via a dedicated wrapper (`run_parlanchina_desktop.py`) or a PyInstaller binary.
* Window is provided by **pywebview**, not a browser.
* Root directory defaults to:

  ```
  ~/.parlanchina
  ```
* A full desktop-app feel.

**Both modes share the same Flask backend and UI.**

---

# 2. PATH RESOLUTION RULES

### The coding agent must *always* use this logic.

Create:

```
parlanchina/paths.py
```

Content:

```python
import os, sys
from pathlib import Path
from enum import Enum


class Mode(str, Enum):
    DEV = "dev"
    DESKTOP = "desktop"


def detect_mode() -> Mode:
    # 1. Explicit env var wins
    env_mode = os.environ.get("PARLANCHINA_MODE")
    if env_mode in ("dev", "desktop"):
        return Mode(env_mode)

    # 2. If frozen (PyInstaller)
    if getattr(sys, "frozen", False):
        return Mode.DESKTOP

    # 3. Default to dev mode
    return Mode.DEV


def get_app_root(mode: Mode | None = None,
                 cli_root: str | None = None) -> Path:

    # Priority 1: --root CLI argument
    if cli_root:
        return Path(cli_root).expanduser().resolve()

    # Priority 2: PARLANCHINA_ROOT environment
    env_root = os.environ.get("PARLANCHINA_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    # Priority 3: mode-based default
    if mode is None:
        mode = detect_mode()

    if mode == Mode.DESKTOP:
        return Path.home().joinpath(".parlanchina").resolve()
    else:
        return Path.cwd().resolve()


def ensure_app_dirs(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "config").mkdir(exist_ok=True)
    return {
        "root": root,
        "logs": root / "logs",
        "data": root / "data",
        "config": root / "config",
    }
```

---

# 3. APPLICATION FACTORY RULES

Create or extend:

```
parlanchina/__init__.py
parlanchina/routes.py
parlanchina/mcp_routes.py
```

**Mandatory** application factory:

```python
# parlanchina/app.py (ADD THIS FILE)
from flask import Flask
from pathlib import Path

def create_app(app_root: Path, dirs: dict):
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static")
    )

    app.config["APP_ROOT"] = app_root
    app.config["DIRS"] = dirs

    # Load config if exists
    from parlanchina.config import load_config
    app.config.update(load_config(dirs["config"]))

    # Register core routes
    from parlanchina.routes import bp as base_routes
    app.register_blueprint(base_routes)

    # Register MCP routes
    from parlanchina.mcp_routes import bp as mcp_bp
    app.register_blueprint(mcp_bp)

    return app
```

---

# 4. DEV MODE ENTRYPOINT

Create:

```
parlanchina/__main__.py
```

```python
from parlanchina.paths import get_app_root, ensure_app_dirs, Mode
from parlanchina.app import create_app

def main():
    root = get_app_root(mode=Mode.DEV)
    dirs = ensure_app_dirs(root)
    app = create_app(root, dirs)
    app.run(host="127.0.0.1", port=5000, debug=True)

if __name__ == "__main__":
    main()
```

Running:

```
./parlanchina.sh
```

---

# 5. DESKTOP MODE WRAPPER

Create:

```
run_parlanchina_desktop.py
```

```python
import os, argparse, threading
import webview

from parlanchina.paths import get_app_root, ensure_app_dirs, Mode
from parlanchina.app import create_app

PORT = 5000

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--root")
    return p.parse_args()

def start_flask(cli_root):
    os.environ.setdefault("PARLANCHINA_MODE", "desktop")

    root = get_app_root(mode=Mode.DESKTOP, cli_root=cli_root)
    dirs = ensure_app_dirs(root)

    app = create_app(root, dirs)
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)

if __name__ == "__main__":
    args = parse_args()

    t = threading.Thread(
        target=start_flask,
        args=(args.root,),
        daemon=True
    )
    t.start()

    webview.create_window("Parlanchina", f"http://127.0.0.1:{PORT}")
    webview.start()
```

---

# 6. STATIC & TEMPLATE CONVENTIONS (FIXED BY LAYOUT)

The coding agent must respect:

* Templates live at

  ```
  parlanchina/templates/*.html
  ```
* Static files live at

  ```
  parlanchina/static/
      favicon/
      images/
      js/
  ```
* No reorganization allowed.

Flask must reference these exact paths.

---

# 7. SERVICES LAYER

All backend logic must be under:

```
parlanchina/services/
```

Required contracts:

### chat_store.py

* Append chat messages to `<root>/data/history.jsonl`
* Return chat history.

### image_store.py

* Manage generated images.
* Store under `<root>/data/images/` if needed.

### llm.py

* Interface to model backends (OpenAI, local, etc.).

### internal_tools.py

* Tools exposed to the UI.

### mcp_manager.py

* Manages MCP connections based on `mcp.json`.

---

# 8. CONFIG RULES

Create:

```
parlanchina/config.py
```

Supports:

* JSON or YAML in `<root>/config/`
* Defaults if no file exists

```python
import json, yaml
from pathlib import Path

def load_config(config_dir: Path):
    cfg_json = config_dir / "settings.json"
    cfg_yaml = config_dir / "settings.yaml"

    if cfg_json.exists():
        return json.loads(cfg_json.read_text())

    if cfg_yaml.exists():
        return yaml.safe_load(cfg_yaml.read_text())

    return {}  # defaults
```

---

# 9. LOGGING RULES

All logs must go to:

```
<root>/logs/app.log
```

Logging initialization should happen inside `create_app`.

---

# 10. JSONL HISTORY FORMAT

`chat_store.py` must produce JSON lines:

```
{"ts": "...", "role": "user", "text": "..."}
{"ts": "...", "role": "assistant", "text": "..."}
```

---

# 11. MCP ROUTES

`parlanchina/mcp_routes.py` must load and serve:

* The MCP config from **root `mcp.json`** (top-level of repo).
* Tools from `parlanchina/services/mcp_manager.py`.

The agent must *not* relocate MCP configs and tools.

---

# 12. PACKAGING RULES

Use PyInstaller.

### One-folder mode:

```
pyinstaller --noconsole --onedir \
    --name Parlanchina \
    run_parlanchina_desktop.py \
    --add-data "parlanchina/templates:parlanchina/templates" \
    --add-data "parlanchina/static:parlanchina/static"
```

### One-file:

```
pyinstaller --onefile --noconsole \
    --name Parlanchina \
    run_parlanchina_desktop.py \
    --add-data "parlanchina/templates:parlanchina/templates" \
    --add-data "parlanchina/static:parlanchina/static"
```

The agent must ensure:

* All static and template directories are included.
* No part of the app assumes CWD is writable in desktop mode.

---

# 13. UI RULES (CANNOT CHANGE EXISTING LAYOUT)

The following UI files are mandatory and fixed:

```
parlanchina/templates/base.html
parlanchina/templates/chat.html
parlanchina/static/js/stream.js
parlanchina/static/js/theme.js
parlanchina/static/js/mermaid-zoom.js
parlanchina/static/images/logo.png
parlanchina/static/favicon/*
```

The coding agent may add JS/CSS; it may not restructure directories or rename files.

---

# 14. ROUTES (MINIMUM CONTRACT)

`parlanchina/routes.py` must include:

```
GET /
GET /chat
POST /api/message
```

---

# 15. ALLOWED ADDITIONS

* New Python modules inside `parlanchina/`
* New JS/CSS under `static/`
* New templates under `templates/`
* New CLI entry scripts at root
* New desktop features inside `run_parlanchina_desktop.py`

**But no relocation or renaming of existing elements.**

---

# 16. PROHIBITED BEHAVIOUR

The coding agent must never:

* Modify, move, or rename existing folders or files.
* Move templates or static files.
* Write to files outside `get_app_root()` except in dev mode.
* Hardcode absolute paths.
* Assume OS-specific directory structure.

---

# 17. SHORT AGENT CHECKLIST

A coding agent must verify:

* Dev mode correctly uses CWD.
* Desktop mode uses `~/.parlanchina`.
* CLI and environment overrides work.
* WebView loads Flask on localhost.
* Packaging contains templates + static.
* No structure changes.
* All state under `<root>/data` and `<root>/logs`.


