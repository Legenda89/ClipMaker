"""Local settings and OAuth tokens for ClipMaker."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def app_data_dir() -> Path:
    base = Path.home() / "AppData" / "Local" / "ClipMaker"
    base.mkdir(parents=True, exist_ok=True)
    return base


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def youtube_token_path() -> Path:
    return app_data_dir() / "youtube_token.json"


def tiktok_token_path() -> Path:
    return app_data_dir() / "tiktok_token.json"


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(data: dict[str, Any]) -> None:
    path = settings_path()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def update_settings(**kwargs: Any) -> dict[str, Any]:
    data = load_settings()
    data.update(kwargs)
    save_settings(data)
    return data
