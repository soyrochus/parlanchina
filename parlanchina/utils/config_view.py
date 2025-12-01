from __future__ import annotations

import json
from typing import Any, Mapping, Set

from parlanchina.utils.markdown import render_markdown


def build_config_html(
    config_values: Mapping[str, Any] | None,
    env_values: Mapping[str, str] | None,
    derived_env_keys: Set[str] | None = None,
) -> str:
    table_markdown = _build_table(
        config_values or {},
        env_values or {},
        derived_env_keys or set(),
    )
    if not table_markdown:
        return ""
    return render_markdown(table_markdown)


def _build_table(
    config_values: Mapping[str, Any],
    env_values: Mapping[str, str],
    derived_env_keys: Set[str],
) -> str:
    keys = sorted(set(config_values.keys()) | set(env_values.keys()))
    if not keys:
        return "No configuration values detected."

    lines = ["| Parameter | Value | Source |", "| --- | --- | --- |"]

    for key in keys:
        env_present = key in env_values and key not in derived_env_keys
        cfg_present = key in config_values

        if env_present:
            value = env_values[key]
            source = "Environment"
            if cfg_present:
                fallback = _escape_cell(_stringify(config_values[key]))
                source = f"Environment (config: {fallback})"
        elif cfg_present:
            value = _stringify(config_values[key])
            source = "Config file"
        else:
            continue

        lines.append(
            f"| `{key}` | `{_escape_cell(value)}` | {_escape_cell(source)} |"
        )

    return "\n".join(lines)


def _stringify(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _escape_cell(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("|", "\\|")
        .replace("\n", "<br>")
    )
