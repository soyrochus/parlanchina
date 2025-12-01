import os
import sys
from enum import Enum
from pathlib import Path


class Mode(str, Enum):
    DEV = "dev"
    DESKTOP = "desktop"


def detect_mode() -> Mode:
    # 1. Explicit env var wins
    env_mode = os.environ.get("PARLANCHINA_MODE")
    if env_mode in ("dev", "desktop"):
        return Mode(env_mode)

    # 2. If frozen (PyInstaller)
    if getattr(sys, "frozen", False):
        return Mode.DESKTOP

    # 3. Default to dev mode
    return Mode.DEV


def get_app_root(mode: Mode | None = None, cli_root: str | None = None) -> Path:
    # Priority 1: --root CLI argument
    if cli_root:
        return Path(cli_root).expanduser().resolve()

    # Priority 2: PARLANCHINA_ROOT environment
    env_root = os.environ.get("PARLANCHINA_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    # Priority 3: mode-based default
    if mode is None:
        mode = detect_mode()

    if mode == Mode.DESKTOP:
        return Path.home().joinpath(".parlanchina").resolve()
    else:
        return Path.cwd().resolve()


def ensure_app_dirs(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "config").mkdir(exist_ok=True)
    return {
        "root": root,
        "logs": root / "logs",
        "data": root / "data",
        "config": root / "config",
    }
