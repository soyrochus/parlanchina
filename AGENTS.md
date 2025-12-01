# AGENT SPEC: Desktop-only Security (Parlanchina)

This document defines how a **code generation agent** (Copilot, Codex, etc.) must implement and preserve the security model that separates:

- **Desktop access** via PyWebView (allowed to call sensitive endpoints).
- **Browser access** via normal web browsers (must be denied by default).

The mechanism is based on:

1. A per-process **desktop security token**.
2. A custom **User-Agent** containing that token for PyWebView.
3. A **Flask guard** that only allows requests with the correct token.
4. A `PARLANCHINA_DEBUG=1` override that disables the guard for debugging.

The token is **not user configurable**.

---

## 1. Core rules (do not break)

Critical:

- The agent MUST NOT break any existing functionality!

- The agent MUST TREAT all provided source code as EXAMPLES, NOT implementation instructions. 

Furthermore, the agent must ensure:

1. On **desktop (PyWebView)**:
   - A random security token is generated once per process.
   - PyWebView is created with a **User-Agent that embeds this token**.
   - All sensitive Flask endpoints are protected by a decorator that validates this token.

2. On **normal browser**:
   - There is no way to obtain or guess the token from configuration.
   - Sensitive endpoints **reply 403** by default.

3. On **debug runs**:
   - If `PARLANCHINA_DEBUG=1` is set in the environment:
     - The token check is bypassed.
     - Sensitive endpoints are reachable from a normal browser for development/testing.

4. The token must **never be exposed** in UI, logs, or configuration files intended for users.

---

## 2. Configuration module

Create or extend a central config module, e.g. `config.py`:

```python
# config.py
import os
import secrets

# Debug flag: when "1", desktop security is disabled
DEBUG_MODE: bool = os.getenv("PARLANCHINA_DEBUG") == "1"

# Per-process desktop token, not user-configurable
_DESKTOP_TOKEN_ENV = os.getenv("PARLANCHINA_DESKTOP_TOKEN")
DESKTOP_TOKEN: str = _DESKTOP_TOKEN_ENV or secrets.token_urlsafe(16)

# The full UA string that pywebview must use
DESKTOP_USER_AGENT: str = f"ParlanchinaDesktop/{DESKTOP_TOKEN}"
````

Notes for the agent:

* `DESKTOP_TOKEN` is generated **once** at process start.
* The code must always refer to `config.DESKTOP_TOKEN` and `config.DESKTOP_USER_AGENT`, never hard-code strings.
* `PARLANCHINA_DESKTOP_TOKEN` is optional, mainly for automated tests; do not document it for users.

---

## 3. Desktop launcher (PyWebView)

In the desktop entrypoint (e.g. `main_desktop.py`), the agent must:

1. Ensure the Flask app is running (whatever mechanism is already used).
2. Create the PyWebView window with the configured `DESKTOP_USER_AGENT`.

Example:

```python
# main_desktop.py
import webview
from config import DESKTOP_USER_AGENT

def main():
    window = webview.create_window(
        "Parlanchina",
        "http://127.0.0.1:5000",
        user_agent=DESKTOP_USER_AGENT,
    )
    webview.start()

if __name__ == "__main__":
    main()
```

This means **every request** coming from the embedded desktop UI will carry a User-Agent containing `DESKTOP_TOKEN`.

---

## 4. Flask security guard

The agent must provide a reusable decorator that enforces the desktop-only rule.
Create `security.py` (or similar):

```python
# security.py
from functools import wraps
from flask import request, abort
from config import DEBUG_MODE, DESKTOP_TOKEN

def is_desktop_request() -> bool:
    """
    Returns True if this request should be treated as coming from
    the trusted desktop UI.
    """
    if DEBUG_MODE:
        # In debug mode, accept everything (for development)
        return True

    ua = request.headers.get("User-Agent", "")
    return DESKTOP_TOKEN in ua

def desktop_only(f):
    """
    Decorator for endpoints that must only be reachable
    from the desktop (PyWebView) or when PARLANCHINA_DEBUG=1.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_desktop_request():
            abort(403)  # Forbidden for normal browsers
        return f(*args, **kwargs)
    return wrapper
```

### Usage on sensitive endpoints

The agent must **always** apply `@desktop_only` to any endpoint that:

* Exposes local filesystem access (listing directories, reading files, selecting workspace roots).
* Performs any operation that should not be accessible from a remote browser.

Example:

```python
# routes/files.py
from flask import Blueprint, request, jsonify
from security import desktop_only

bp = Blueprint("files", __name__, url_prefix="/api/files")

@bp.route("/list", methods=["POST"])
@desktop_only
def list_files():
    # Implementation that touches local filesystem
    ...

@bp.route("/read_text", methods=["POST"])
@desktop_only
def read_text():
    # Implementation that reads local files
    ...
```

If new sensitive endpoints are added later, they must also use `@desktop_only`.

---

## 5. Debug mode behaviour

Setting:

```bash
export PARLANCHINA_DEBUG=1
```

before starting the app must:

* Make `config.DEBUG_MODE` be `True`.
* Make `security.is_desktop_request()` always return `True`.
* Allow sensitive endpoints to be accessible via normal browser (for development, testing, or manual inspection).

The agent must not add any additional user configuration for this.
The only supported switch is `PARLANCHINA_DEBUG=1`.

---

## 6. Frontend and documentation expectations

From the frontend perspective:

* The desktop UI (PyWebView) works transparently; it sends the special User-Agent automatically.
* A user opening `http://127.0.0.1:5000` in a normal browser:

  * Can still access **non-sensitive** endpoints (e.g. basic chat).
  * Will get **403 Forbidden** on any endpoint marked `@desktop_only`.

The agent must **not** generate UI code that assumes browser access to the protected endpoints.
If such access is needed in tests or experiments, `PARLANCHINA_DEBUG=1` should be used instead.

---

## 7. Invariants to preserve

The code generation agent should treat these as **invariants**:

1. `config.DESKTOP_TOKEN` is the **single source of truth** for the token.
2. `config.DESKTOP_USER_AGENT` is the **only** UA value used for PyWebView.
3. All sensitive endpoints are decorated with `@desktop_only`.
4. No other configuration or runtime flag weakens or bypasses the guard, except:

   * `PARLANCHINA_DEBUG=1` for development.

Any refactor or new code touching security must continue to respect these invariants.


