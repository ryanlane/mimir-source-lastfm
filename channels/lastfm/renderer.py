"""HTML-based Last.fm renderer using Jinja2 + html_renderer_service (Playwright)."""

import base64
import logging
from pathlib import Path
from typing import Optional

import requests as _req

logger = logging.getLogger("mimir.channels.lastfm.renderer")

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_LASTFM_PLACEHOLDER = "2a96cbd8b46e442fc41c2b86b821562f"


class LastfmHtmlRenderer:
    def __init__(self):
        self._jinja = self._make_jinja()
        self._art_cache: dict = {}

    def _make_jinja(self):
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
            return Environment(
                loader=FileSystemLoader(str(_TEMPLATE_DIR)),
                autoescape=select_autoescape(["html"]),
            )
        except ImportError:
            logger.warning("[lastfm] jinja2 not installed — install it with: pip install jinja2")
            return None

    def _art_b64(self, art_url: Optional[str]) -> Optional[str]:
        if not art_url or _LASTFM_PLACEHOLDER in art_url:
            return None
        if art_url in self._art_cache:
            return self._art_cache[art_url]
        try:
            resp = _req.get(art_url, timeout=8)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            b64 = base64.b64encode(resp.content).decode()
            data_uri = f"data:{ct};base64,{b64}"
            self._art_cache[art_url] = data_uri
            return data_uri
        except Exception as exc:
            logger.debug("[lastfm] album art fetch failed: %s", exc)
            return None

    def _layout_for(self, width: int, height: int, square_style: str) -> str:
        aspect = width / height
        if aspect >= 1.2:
            return "landscape"
        if aspect <= 0.85:
            return "portrait"
        return "square-details" if square_style == "with_details" else "square"

    async def render(
        self,
        track: str,
        artist: str,
        album: str,
        art_url: Optional[str],
        is_playing: bool,
        width: int,
        height: int,
        theme: str,
        square_style: str = "art_only",
    ) -> bytes:
        if self._jinja is None:
            raise RuntimeError("jinja2 not installed — run: pip install jinja2")

        try:
            from app.services.html_renderer import html_renderer_service, HtmlRendererUnavailableError
        except ImportError as exc:
            raise RuntimeError("html_renderer_service not available (not running inside Mimir server)") from exc

        if not html_renderer_service.available:
            from app.services.html_renderer import HtmlRendererUnavailableError
            raise HtmlRendererUnavailableError("Chromium renderer not running")

        layout = self._layout_for(width, height, square_style)
        art = self._art_b64(art_url)

        template = self._jinja.get_template("lastfm.html")
        html = template.render(
            layout=layout,
            theme=theme,
            width=width,
            height=height,
            track=track,
            artist=artist,
            album=album,
            art=art,
            is_playing=is_playing,
        )

        return await html_renderer_service.render(html, width, height)


_renderer = LastfmHtmlRenderer()


async def render(
    track: str,
    artist: str,
    album: str,
    art_url: Optional[str],
    is_playing: bool,
    width: int,
    height: int,
    theme: str,
    square_style: str = "art_only",
) -> bytes:
    return await _renderer.render(
        track=track,
        artist=artist,
        album=album,
        art_url=art_url,
        is_playing=is_playing,
        width=width,
        height=height,
        theme=theme,
        square_style=square_style,
    )
