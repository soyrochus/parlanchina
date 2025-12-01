import argparse
import os
import platform
import threading
import time
import webbrowser
from pathlib import Path

from parlanchina.app import create_app
from parlanchina.paths import Mode, ensure_app_dirs, get_app_root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Parlanchina in desktop or dev mode.")
    parser.add_argument("mode", nargs="?", choices=("desktop", "dev"), default="desktop")
    parser.add_argument("--root", help="Override the application root directory.")
    parser.add_argument("--host", default="127.0.0.1", help="Hostname to bind the server to.")
    parser.add_argument("--port", type=int, default=5000, help="Port for the Flask server.")
    parser.add_argument("--debug", dest="debug", action="store_true", help="Enable Flask debug mode.")
    parser.add_argument("--no-debug", dest="debug", action="store_false", help="Disable Flask debug mode explicitly.")
    parser.set_defaults(debug=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    mode = Mode.DESKTOP if args.mode == "desktop" else Mode.DEV

    if mode == Mode.DESKTOP:
        _run_desktop(args)
    else:
        _run_dev(args)


def _run_dev(args: argparse.Namespace) -> None:
    os.environ.setdefault("PARLANCHINA_MODE", "dev")
    root = get_app_root(mode=Mode.DEV, cli_root=args.root)
    _load_dev_dotenv(root)
    dirs = ensure_app_dirs(root)
    app = create_app(root, dirs)

    debug = True if args.debug is None else args.debug

    app.run(
        host=args.host,
        port=args.port,
        debug=debug,
        use_reloader=debug,
        threaded=True,
    )


def _run_desktop(args: argparse.Namespace) -> None:
    os.environ.setdefault("PARLANCHINA_MODE", "desktop")
    debug = False if args.debug is None else args.debug

    def _start_server() -> None:
        root = get_app_root(mode=Mode.DESKTOP, cli_root=args.root)
        dirs = ensure_app_dirs(root)
        app = create_app(root, dirs)
        app.run(
            host=args.host,
            port=args.port,
            debug=debug,
            use_reloader=False,
            threaded=True,
        )

    server_thread = threading.Thread(target=_start_server, daemon=True)
    server_thread.start()
    _launch_webview(args.host, args.port, debug)


def _launch_webview(host: str, port: int, debug: bool) -> None:
    try:
        import webview
        from webview.errors import WebViewException
    except ImportError:
        print("[Parlanchina] pywebview not available, opening default browser instead")
        webbrowser.open(f"http://{host}:{port}")
        return

    system = platform.system().lower()
    gui_backend = "qt" if system == "linux" else None

    try:
        webview.create_window(
            "Parlanchina",
            f"http://{host}:{port}",
            width=1200,
            height=800,
            min_size=(800, 600),
        )
        webview.start(gui=gui_backend, debug=debug, http_server=True)
    except WebViewException as exc:
        print(f"[Parlanchina] WebView failed ({exc!r}), falling back to browser")
        webbrowser.open(f"http://{host}:{port}")


def _load_dev_dotenv(root: Path) -> None:
    dotenv_path = root / ".env"
    if not dotenv_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(dotenv_path=str(dotenv_path), override=False)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
