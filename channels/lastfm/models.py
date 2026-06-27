"""Settings model for the Last.fm channel."""
from __future__ import annotations

from dataclasses import dataclass

from .mimir_utils import SettingsMixin


@dataclass
class Settings(SettingsMixin):
    username: str = ""
    api_key: str = ""
    show_last_played: bool = True
    theme: str = "dark"
    square_style: str = "art_only"
