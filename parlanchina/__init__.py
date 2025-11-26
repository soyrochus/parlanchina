import os
from pathlib import Path

from asgiref.wsgi import WsgiToAsgi
from dotenv import load_dotenv
from flask import Flask


def create_app() -> Flask:
    """Application factory for Parlanchina."""
    load_dotenv()

    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    app.config["DATA_DIR"] = Path(app.root_path).parent / "data" / "sessions"
    app.config["PARLANCHINA_MODELS"] = _parse_models(
        os.getenv("PARLANCHINA_MODELS", "")
    )
    app.config["PARLANCHINA_DEFAULT_MODEL"] = os.getenv(
        "PARLANCHINA_DEFAULT_MODEL", ""
    )

    # Ensure persistence directory exists.
    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)

    from parlanchina import routes

    app.register_blueprint(routes.bp)

    return app


def _parse_models(raw: str) -> list[str]:
    models = [part.strip() for part in raw.split(",") if part.strip()]
    return models


# Module-level app instance for ASGI servers
# Wrap Flask app with ASGI adapter
app = WsgiToAsgi(create_app())
