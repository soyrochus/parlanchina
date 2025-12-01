import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask

from parlanchina.config import load_config
from parlanchina.paths import Mode, detect_mode
from parlanchina.utils.banner import load_banner_html
from parlanchina.utils.config_view import build_config_html

_DESKTOP_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENAI_PROVIDER",
    "OPENAI_API_BASE",
    "OPENAI_API_VERSION",
    "PARLANCHINA_MODELS",
    "PARLANCHINA_DEFAULT_MODEL",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "LOG_TYPE",
    "LOG_FILE",
}

_LOG_DEFAULTS = {
    "LOG_LEVEL": "INFO",
    "LOG_FORMAT": "%(asctime)s %(levelname)s %(name)s: %(message)s",
    "LOG_TYPE": "file",
    "LOG_FILE": "app.log",
}


def _configure_logging(log_dir: Path, options: dict[str, str]) -> None:
    """Configure logging based on resolved options."""

    level_name = (options.get("LOG_LEVEL") or _LOG_DEFAULTS["LOG_LEVEL"]).upper()
    level = getattr(logging, level_name, logging.INFO)

    log_format = options.get("LOG_FORMAT") or _LOG_DEFAULTS["LOG_FORMAT"]
    log_type = (options.get("LOG_TYPE") or _LOG_DEFAULTS["LOG_TYPE"]).lower()
    log_file_name = options.get("LOG_FILE") or _LOG_DEFAULTS["LOG_FILE"]

    handlers: list[logging.Handler] = []
    if log_type == "stream":
        handlers.append(logging.StreamHandler())
    elif log_type == "both":
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.StreamHandler())
        handlers.append(
            logging.FileHandler(_resolve_log_path(log_dir, log_file_name), encoding="utf-8")
        )
    else:  # default to file logging
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(_resolve_log_path(log_dir, log_file_name), encoding="utf-8")
        )

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=handlers,
        force=True,
    )


def _resolve_log_path(log_dir: Path, file_name: str) -> Path:
    path = Path(file_name)
    if not path.is_absolute():
        return log_dir / path
    return path


def create_app(app_root: Path, dirs: dict) -> Flask:
    templates_path = Path(__file__).parent / "templates"
    static_path = Path(__file__).parent / "static"

    raw_config = load_config(dirs["config"]) or {}
    if not isinstance(raw_config, dict):
        raw_config = {}
    config_values: dict[str, Any] = dict(raw_config)

    mode = detect_mode()
    injected_env_keys: set[str] = set()
    if mode == Mode.DESKTOP:
        injected_env_keys = _apply_desktop_config_env(config_values)

    log_options = _resolve_logging_options(config_values)
    _configure_logging(dirs["logs"], log_options)

    app = Flask(
        __name__,
        template_folder=str(templates_path),
        static_folder=str(static_path),
    )

    app.config["APP_ROOT"] = app_root
    app.config["DIRS"] = dirs

    data_root = dirs["data"]
    app.config["DATA_DIR"] = data_root / "sessions"
    app.config["IMAGE_DIR"] = data_root / "images"
    app.config["PARLANCHINA_MODELS"] = []
    app.config["PARLANCHINA_DEFAULT_MODEL"] = ""

    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["IMAGE_DIR"].mkdir(parents=True, exist_ok=True)

    app.config.update({k: v for k, v in config_values.items() if k not in {
        "PARLANCHINA_MODELS",
        "PARLANCHINA_DEFAULT_MODEL",
        "DATA_DIR",
        "IMAGE_DIR",
    }})

    app.config["PARLANCHINA_MODELS"] = _resolve_models(config_values)
    app.config["PARLANCHINA_DEFAULT_MODEL"] = _resolve_default_model(config_values)
    app.config["RAW_CONFIG"] = raw_config
    app.config["BANNER_HTML"] = load_banner_html()

    env_snapshot_keys = set(_DESKTOP_ENV_KEYS)
    env_snapshot_keys.update({
        "PARLANCHINA_MODE",
        "PARLANCHINA_ROOT",
    })
    env_snapshot = {
        key: value
        for key in sorted(env_snapshot_keys)
        if (value := os.environ.get(key))
    }

    app.config["CONFIG_HTML"] = build_config_html(
        config_values,
        env_snapshot,
        injected_env_keys,
    )

    from parlanchina.routes import bp as base_routes
    from parlanchina.mcp_routes import bp as mcp_bp

    app.register_blueprint(base_routes)
    app.register_blueprint(mcp_bp)

    @app.context_processor
    def _inject_banner() -> dict[str, Any]:
        return {
            "banner_html": app.config.get("BANNER_HTML", ""),
            "config_html": app.config.get("CONFIG_HTML", ""),
        }

    return app


def _parse_models(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _apply_desktop_config_env(config_values: dict[str, Any]) -> set[str]:
    """Populate environment defaults from desktop configuration when unset."""

    injected: set[str] = set()
    for key in _DESKTOP_ENV_KEYS:
        if os.getenv(key):
            continue
        if key not in config_values:
            continue
        value = config_values[key]
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            serialized = ",".join(_stringify(item) for item in value if _stringify(item))
        else:
            serialized = _stringify(value)
        if not serialized:
            continue
        os.environ[key] = serialized
        injected.add(key)

    return injected


def _resolve_logging_options(config_values: dict[str, Any]) -> dict[str, str]:
    options: dict[str, str] = {}
    for key, default in _LOG_DEFAULTS.items():
        env_value = os.getenv(key)
        cleaned_env = _stringify(env_value) if env_value is not None else ""
        if cleaned_env:
            options[key] = cleaned_env
            continue
        config_value = config_values.get(key)
        if isinstance(config_value, (list, tuple)):
            config_value = ",".join(_stringify(item) for item in config_value if _stringify(item))
        cleaned_config = _stringify(config_value) if config_value is not None else ""
        if not cleaned_config:
            options[key] = default
        else:
            options[key] = cleaned_config
    return options


def _resolve_models(config_values: dict[str, Any]) -> list[str]:
    env_value = os.getenv("PARLANCHINA_MODELS")
    if env_value:
        return _parse_models(env_value)

    config_value = config_values.get("PARLANCHINA_MODELS")
    if isinstance(config_value, (list, tuple)):
        return [str(item).strip() for item in config_value if str(item).strip()]
    if isinstance(config_value, str):
        return _parse_models(config_value)
    return []


def _resolve_default_model(config_values: dict[str, Any]) -> str:
    env_value = os.getenv("PARLANCHINA_DEFAULT_MODEL")
    if env_value:
        return env_value

    config_value = config_values.get("PARLANCHINA_DEFAULT_MODEL")
    if config_value is None:
        return ""
    return str(config_value)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(_stringify(item) for item in value if _stringify(item))
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text
