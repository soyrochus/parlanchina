import base64
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, send_from_directory


@dataclass
class ImageMeta:
    id: str
    filename: str
    url_path: str
    created_at: str


def _image_dir() -> Path:
    return current_app.config["IMAGE_DIR"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_image_from_base64(image_b64: str, ext: str = "png") -> ImageMeta:
    if not image_b64:
        raise ValueError("image_b64 is required")

    directory = _image_dir()
    directory.mkdir(parents=True, exist_ok=True)

    image_id = uuid.uuid4().hex
    filename = f"{image_id}.{ext}".lower()
    path = directory / filename

    data = base64.b64decode(image_b64)
    with path.open("wb") as f:
        f.write(data)

    return ImageMeta(
        id=image_id,
        filename=filename,
        url_path=f"/images/{filename}",
        created_at=_now(),
    )


def serve_image(filename: str):
    return send_from_directory(_image_dir(), filename)
