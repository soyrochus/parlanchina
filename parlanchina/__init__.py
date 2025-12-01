from pathlib import Path

from asgiref.wsgi import WsgiToAsgi
from dotenv import load_dotenv

from parlanchina.paths import Mode


def _maybe_load_dev_dotenv(root: Path, mode: Mode) -> None:
    if mode != Mode.DEV:
        return
    dotenv_path = root / ".env"
    if not dotenv_path.exists():
        return
    load_dotenv(dotenv_path=str(dotenv_path), override=False)


from parlanchina.app import create_app as _create_app
from parlanchina.paths import Mode, detect_mode, ensure_app_dirs, get_app_root


def create_app():
    mode = detect_mode()
    root = get_app_root(mode=mode)
    _maybe_load_dev_dotenv(root, mode)
    dirs = ensure_app_dirs(root)
    return _create_app(root, dirs)


app = WsgiToAsgi(create_app())
