import os
import os
from pathlib import Path

from asgiref.wsgi import WsgiToAsgi
from dotenv import load_dotenv
from flask import Flask


def create_app() -> Flask:
    """Application factory for Parlanchina."""

    load_dotenv()

    # --- Logging configuration ---
    import logging
    log_level = os.getenv("LOG_LEVEL", "WARNING").upper()
    log_format = os.getenv("LOG_FORMAT", "%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_type = os.getenv("LOG_TYPE", "stream").lower()  # 'stream' or 'file'
    log_file = os.getenv("LOG_FILE", "parlanchina.log")

    if log_type == "file":
        logging.basicConfig(
            level=log_level,
            format=log_format,
            filename=log_file,
            filemode="a"
        )
    else:
        logging.basicConfig(
            level=log_level,
            format=log_format
        )

    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    app.config["DATA_DIR"] = Path(app.root_path).parent / "data" / "sessions"
    app.config["IMAGE_DIR"] = Path(app.root_path).parent / "data" / "images"
    app.config["PARLANCHINA_MODELS"] = _parse_models(
        os.getenv("PARLANCHINA_MODELS", "")
    )
    app.config["PARLANCHINA_DEFAULT_MODEL"] = os.getenv(
        "PARLANCHINA_DEFAULT_MODEL", ""
    )

    # Ensure persistence directory exists.
    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["IMAGE_DIR"].mkdir(parents=True, exist_ok=True)

    from parlanchina import routes

    app.register_blueprint(routes.bp)

    return app


def _parse_models(raw: str) -> list[str]:
    models = [part.strip() for part in raw.split(",") if part.strip()]
    return models


# Module-level app instance for ASGI servers
# Wrap Flask app with ASGI adapter
app = WsgiToAsgi(create_app())
