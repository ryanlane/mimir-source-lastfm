"""Tests for the Last.fm channel models — verifies mimir_utils migration."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from channels.lastfm.models import Settings


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.username == ""
        assert s.api_key == ""
        assert s.show_last_played is True
        assert s.theme == "dark"
        assert s.square_style == "art_only"

    def test_to_public_dict_masks_api_key(self):
        s = Settings(api_key="lastfm-secret-key-abc1234")
        pub = s.to_public_dict()
        assert pub["api_key"].startswith("••••••••")
        assert "lastfm" not in pub["api_key"]
        assert "secret" not in pub["api_key"]

    def test_to_public_dict_empty_key(self):
        s = Settings(api_key="")
        pub = s.to_public_dict()
        assert pub["api_key"] == ""

    def test_to_public_dict_short_key(self):
        s = Settings(api_key="abc")
        pub = s.to_public_dict()
        assert pub["api_key"] == "••••••••"

    def test_from_dict_ignores_unknown(self):
        s = Settings.from_dict({"username": "scrobbler", "unknown_field": True, "api_key": "k"})
        assert s.username == "scrobbler"
        assert s.api_key == "k"

    def test_from_dict_partial(self):
        s = Settings.from_dict({"username": "only"})
        assert s.theme == "dark"
        assert s.show_last_played is True

    def test_from_dict_full(self):
        s = Settings.from_dict({
            "username": "testuser",
            "api_key": "secret",
            "show_last_played": False,
            "theme": "light",
            "square_style": "with_text",
        })
        assert s.show_last_played is False
        assert s.theme == "light"

    def test_to_dict_round_trips(self):
        s = Settings(username="user1", api_key="k", theme="light")
        s2 = Settings.from_dict(s.to_dict())
        assert s2.username == "user1"
        assert s2.theme == "light"

    def test_settings_persist_to_disk(self, tmp_path):
        p = tmp_path / "settings.json"
        s = Settings(username="diskuser", api_key="mykey", theme="light")
        p.write_text(json.dumps(s.to_dict(), indent=2))
        s2 = Settings.from_dict(json.loads(p.read_text()))
        assert s2.username == "diskuser"
        assert s2.theme == "light"

    def test_merge_via_from_dict(self):
        s = Settings(username="original", theme="dark")
        merged = Settings.from_dict({**s.to_dict(), "theme": "light"})
        assert merged.username == "original"
        assert merged.theme == "light"
