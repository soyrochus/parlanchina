from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Optional

from parlanchina.utils.markdown import render_markdown


def load_banner_text() -> Optional[str]:
    """Return the raw banner markdown (comments stripped) if available."""
    for banner_path in _candidate_paths():
        if not banner_path.exists():
            continue
        try:
            raw_text = banner_path.read_text(encoding="utf-8")
        except OSError:
            continue
        cleaned = _strip_comments(raw_text)
        cleaned = cleaned.strip()
        if cleaned:
            return cleaned
    return None


def load_banner_html() -> Optional[str]:
    """Render the banner markdown to sanitized HTML for UI display."""
    banner_text = load_banner_text()
    if not banner_text:
        return None
    return render_markdown(banner_text)


def _candidate_paths() -> Iterable[Path]:
    base = Path(__file__).resolve()
    frozen_base = getattr(sys, "_MEIPASS", None)
    roots = [
        base.parent.parent.parent,  # project root when running from source
        base.parent.parent,  # inside packaged parlanchina/ directory
        Path.cwd(),
        Path(frozen_base) if frozen_base else None,
    ]
    seen: set[Path] = set()
    for root in roots:
        if root is None:
            continue
        try:
            banner_path = (root / "banner.md").resolve()
        except OSError:
            continue
        if banner_path in seen:
            continue
        seen.add(banner_path)
        yield banner_path


def _strip_comments(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            continue
        lines.append(raw_line)
    return "\n".join(lines)
