"""Last.fm Now Playing channel for Mimir."""

import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import renderer as _renderer

logger = logging.getLogger(__name__)

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"


class LastfmChannel:
    def __init__(self, channel_dir: str, config: Optional[Dict[str, Any]] = None):
        self.channel_dir = Path(channel_dir)
        self.data_dir = self.channel_dir / "data"
        self.data_dir.mkdir(exist_ok=True)
        self._settings_path = self.data_dir / "settings.json"
        self.settings = self._load_settings()
        if config:
            self.settings.update(config)
        self._save_settings()
        self._image_cache: Dict[str, Dict[str, Any]] = {}

    # ── Settings ──────────────────────────────────────────────────────────────

    def _load_settings(self) -> Dict[str, Any]:
        try:
            with open(self._settings_path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "username": "",
                "api_key": "",
                "show_last_played": True,
                "theme": "dark",
            }

    def _save_settings(self) -> None:
        with open(self._settings_path, "w") as f:
            json.dump(self.settings, f, indent=2)

    def _masked_settings(self) -> Dict[str, Any]:
        key = self.settings.get("api_key", "")
        return {
            **self.settings,
            "api_key": ("***" + key[-4:]) if len(key) > 4 else ("***" if key else ""),
            "configured": bool(self.settings.get("username") and self.settings.get("api_key")),
        }

    # ── Last.fm API ───────────────────────────────────────────────────────────

    def _fetch_track(self) -> tuple[Optional[Dict[str, Any]], str]:
        username = self.settings.get("username", "").strip()
        api_key  = self.settings.get("api_key", "").strip()
        if not username or not api_key:
            return None, "not_configured"
        try:
            resp = requests.get(
                LASTFM_API,
                params={
                    "method": "user.getRecentTracks",
                    "user": username,
                    "api_key": api_key,
                    "format": "json",
                    "limit": 1,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("[lastfm] API request failed: %s", exc)
            return None, f"api_error: {exc}"

        if "error" in data:
            return None, f"lastfm_error_{data['error']}: {data.get('message', '')}"

        tracks = data.get("recenttracks", {}).get("track", [])
        if not tracks:
            return None, "no_tracks"

        track = tracks[0] if isinstance(tracks, list) else tracks
        is_playing = track.get("@attr", {}).get("nowplaying") == "true"

        images = track.get("image", [])
        art_url: Optional[str] = None
        for size in ("extralarge", "large", "medium"):
            for img in images:
                url = img.get("#text", "")
                if img.get("size") == size and url:
                    art_url = url
                    break
            if art_url:
                break

        artist = track.get("artist", {})
        artist_name = artist.get("#text", "") if isinstance(artist, dict) else str(artist)

        album = track.get("album", {})
        album_name = album.get("#text", "") if isinstance(album, dict) else str(album)

        return {
            "track":      track.get("name", "Unknown"),
            "artist":     artist_name or "Unknown Artist",
            "album":      album_name  or "",
            "art_url":    art_url,
            "is_playing": is_playing,
            "url":        track.get("url", ""),
        }, "ok"

    # ── request_image ─────────────────────────────────────────────────────────

    async def request_image(self, request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rd = request_data or {}
        settings_block = rd.get("settings", {})

        width     = int(settings_block.get("resolution", [800, 480])[0])
        height    = int(settings_block.get("resolution", [800, 480])[1])
        grayscale = bool(settings_block.get("grayscale", False))
        theme     = self.settings.get("theme", "dark")

        track_info, status = self._fetch_track()

        if track_info is None:
            show_last = self.settings.get("show_last_played", True)
            if not show_last or status == "not_configured":
                return {"success": False, "error": status}

        is_playing = track_info["is_playing"] if track_info else False
        if not is_playing and not self.settings.get("show_last_played", True):
            return {"success": False, "error": "nothing_playing"}

        fp_parts = [
            track_info["track"] if track_info else "",
            track_info["artist"] if track_info else "",
            str(is_playing),
        ]
        content_fp = hashlib.md5("|".join(fp_parts).encode()).hexdigest()
        cache_key  = f"{content_fp}|{width}x{height}|{'g' if grayscale else 'c'}|{theme}"

        cached = self._image_cache.get(cache_key)
        if cached:
            return self._build_response(cached, track_info, width, height, grayscale, theme, content_fp, hit=True)

        image = _renderer.render(
            track    = track_info["track"]  if track_info else "",
            artist   = track_info["artist"] if track_info else "",
            album    = track_info["album"]  if track_info else "",
            art_url  = track_info.get("art_url") if track_info else None,
            is_playing = is_playing,
            width    = width,
            height   = height,
            theme    = theme,
        )

        if grayscale:
            image = image.convert("L")

        buf = io.BytesIO()
        try:
            image.save(buf, format="JPEG", quality=95)
            fmt, ct = "jpeg", "image/jpeg"
        except Exception:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            fmt, ct = "png", "image/png"

        raw = buf.getvalue()
        sha = hashlib.sha256(raw).hexdigest()

        entry = {"bytes": raw, "format": fmt, "content_type": ct, "sha256": sha,
                 "description": self._description(track_info, is_playing)}
        self._image_cache[cache_key] = entry

        return self._build_response(entry, track_info, width, height, grayscale, theme, content_fp, hit=False)

    def _description(self, track_info: Optional[Dict], is_playing: bool) -> str:
        if not track_info:
            return "Last.fm: nothing playing"
        verb = "Now playing" if is_playing else "Last played"
        return f"{verb}: {track_info['track']} — {track_info['artist']}"

    def _build_response(self, entry, track_info, width, height, grayscale, theme, fp, hit):
        return {
            "success":            True,
            "bytes":              entry["bytes"],
            "content_type":       entry["content_type"],
            "format":             entry["format"],
            "sha256":             entry["sha256"],
            "preferred_transport": "bytes",
            "width":              width,
            "height":             height,
            "grayscale":          grayscale,
            "description":        entry["description"],
            "track_info":         track_info,
            "content_fingerprint": fp,
            "cache_hit":          hit,
            "timestamp":          datetime.now(timezone.utc).isoformat(),
            "image": {
                "bytes":        entry["bytes"],
                "content_type": entry["content_type"],
                "format":       entry["format"],
                "width":        width,
                "height":       height,
                "sha256":       entry["sha256"],
                "description":  entry["description"],
                "preferred_transport": "bytes",
            },
        }

    # ── FastAPI router ────────────────────────────────────────────────────────

    def build_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/manifest")
        async def manifest():
            plugin_json = self.channel_dir / "plugin.json"
            with open(plugin_json) as f:
                return JSONResponse(json.load(f))

        @router.get("/status")
        async def status():
            track_info, stat = self._fetch_track()
            return JSONResponse({"success": True, "track": track_info, "status": stat})

        @router.get("/settings")
        async def get_settings():
            return JSONResponse({"success": True, "settings": self._masked_settings()})

        @router.put("/settings")
        async def put_settings(request: Request):
            body = await request.json()
            for key in ("username", "api_key", "show_last_played", "theme"):
                if key in body:
                    self.settings[key] = body[key]
            self._save_settings()
            self._image_cache.clear()
            return JSONResponse({"success": True, "settings": self._masked_settings()})

        @router.post("/request-image")
        async def request_image(request: Request):
            body: Dict[str, Any] = {}
            try:
                body = await request.json()
            except Exception:
                pass
            result = await self.request_image(body)
            if not result.get("success"):
                from fastapi import HTTPException
                raise HTTPException(status_code=503, detail=result.get("error", "unknown"))
            raw = result.pop("bytes", b"")
            result.pop("image", None)
            from fastapi.responses import Response
            return Response(content=raw, media_type=result.get("content_type", "image/jpeg"))

        return router
