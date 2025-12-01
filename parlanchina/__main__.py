from parlanchina.app import create_app
from parlanchina.paths import Mode, ensure_app_dirs, get_app_root


def main():
    root = get_app_root(mode=Mode.DEV)
    dirs = ensure_app_dirs(root)
    app = create_app(root, dirs)
    app.run(host="127.0.0.1", port=5000, debug=True)


if __name__ == "__main__":
    main()
