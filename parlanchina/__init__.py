from asgiref.wsgi import WsgiToAsgi

from parlanchina.app import create_app as _create_app
from parlanchina.paths import detect_mode, ensure_app_dirs, get_app_root


def create_app():
    mode = detect_mode()
    root = get_app_root(mode=mode)
    dirs = ensure_app_dirs(root)
    return _create_app(root, dirs)


app = WsgiToAsgi(create_app())
