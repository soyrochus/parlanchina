import argparse
import os
import threading
import platform
import webbrowser

import webview
from webview.errors import WebViewException

from parlanchina.app import create_app
from parlanchina.paths import Mode, ensure_app_dirs, get_app_root

PORT = 5000


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    return parser.parse_args()


def start_flask(cli_root: str | None):
    os.environ.setdefault("PARLANCHINA_MODE", "desktop")

    root = get_app_root(mode=Mode.DESKTOP, cli_root=cli_root)
    dirs = ensure_app_dirs(root)

    app = create_app(root, dirs)
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)


def start_ui():
    system = platform.system().lower()

    # Decide backend: force Qt only on Linux, let pywebview choose elsewhere
    gui_backend: str | None = None
    if system == "linux":
        gui_backend = "qt"

    try:
        webview.create_window(
            "Parlanchina", 
            f"http://127.0.0.1:{PORT}",
            width=1200,
            height=800,
            min_size=(800, 600),
        )
        # On Linux this uses Qt, on macOS/Windows it uses the native default
        webview.start(
            gui=gui_backend,
            debug=False,
            http_server=True,  # Enable HTTP server for better resource loading
        )
    except WebViewException as e:
        # Graceful fallback: open default browser instead of crashing
        print(f"[Parlanchina] WebView failed ({e!r}), falling back to browser")
        webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    args = parse_args()

    flask_thread = threading.Thread(
        target=start_flask,
        args=(args.root,),
        daemon=True,
    )
    flask_thread.start()

    start_ui()
