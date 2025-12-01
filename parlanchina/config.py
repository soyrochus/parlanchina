import json
from pathlib import Path
from typing import Any

import yaml


def load_config(config_dir: Path) -> dict[str, Any]:
    cfg_json = config_dir / "settings.json"
    cfg_yaml = config_dir / "settings.yaml"

    if cfg_json.exists():
        return json.loads(cfg_json.read_text())

    if cfg_yaml.exists():
        return yaml.safe_load(cfg_yaml.read_text())

    return {}
