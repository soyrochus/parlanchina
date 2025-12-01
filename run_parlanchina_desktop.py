import argparse
import os
import threading

import webview

from parlanchina.app import create_app
from parlanchina.paths import Mode, ensure_app_dirs, get_app_root

PORT = 5000


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    return parser.parse_args()


def start_flask(cli_root):
    os.environ.setdefault("PARLANCHINA_MODE", "desktop")

    root = get_app_root(mode=Mode.DESKTOP, cli_root=cli_root)
    dirs = ensure_app_dirs(root)

    app = create_app(root, dirs)
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    args = parse_args()

    flask_thread = threading.Thread(
        target=start_flask,
        args=(args.root,),
        daemon=True,
    )
    flask_thread.start()

    webview.create_window("Parlanchina", f"http://127.0.0.1:{PORT}")
    webview.start()
