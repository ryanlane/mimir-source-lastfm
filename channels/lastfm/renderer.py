"""Pillow-based renderer for Last.fm now-playing cards."""

import io
import logging
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

logger = logging.getLogger(__name__)

LASTFM_RED  = (186, 0, 0)
DARK_BG     = (13, 13, 13)
LIGHT_BG    = (245, 245, 245)
TEXT_WHITE  = (255, 255, 255)
TEXT_BLACK  = (15, 15, 15)
TEXT_GRAY_D = (170, 170, 170)
TEXT_GRAY_L = (90, 90, 90)
IDLE_OVERLAY = (0, 0, 0, 140)   # semi-transparent black for "not playing" dim

FONT_SEARCH = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _find_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [p for p in FONT_SEARCH if ("Bold" in p or "bold" in p) == bold] + FONT_SEARCH
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    # Local bundled fonts (optional — copy from mimir-channel-spotify)
    local = Path(__file__).parent / "fonts"
    for ttf in sorted(local.glob("*.ttf")):
        try:
            return ImageFont.truetype(str(ttf), size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _fetch_art(url: str, size: tuple[int, int]) -> Optional[Image.Image]:
    if not url or url.endswith("2a96cbd8b46e442fc41c2b86b821562f.png"):
        return None  # Last.fm placeholder
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        return img.resize(size, Image.LANCZOS)
    except Exception as exc:
        logger.warning("Album art fetch failed (%s): %s", url, exc)
        return None


def _placeholder_art(size: tuple[int, int], color: tuple = (40, 40, 40)) -> Image.Image:
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    font = _find_font(max(12, size[0] // 8))
    draw.text((size[0] // 2, size[1] // 2), "♫", fill=(80, 80, 80), font=font, anchor="mm")
    return img


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        w = draw.textlength(test, font=font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def render(
    track: str,
    artist: str,
    album: str,
    art_url: Optional[str],
    is_playing: bool,
    width: int,
    height: int,
    theme: str = "dark",
) -> Image.Image:
    dark = theme == "dark"
    bg_color   = DARK_BG  if dark else LIGHT_BG
    text_main  = TEXT_WHITE if dark else TEXT_BLACK
    text_sub   = TEXT_GRAY_D if dark else TEXT_GRAY_L

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img, "RGBA")

    aspect = width / height

    if aspect >= 1.3:
        _render_landscape(img, draw, track, artist, album, art_url, is_playing,
                          width, height, dark, text_main, text_sub)
    elif aspect <= 0.77:
        _render_portrait(img, draw, track, artist, album, art_url, is_playing,
                         width, height, dark, text_main, text_sub)
    else:
        _render_square(img, draw, track, artist, album, art_url, is_playing,
                       width, height, dark, text_main, text_sub)

    return img


def _render_landscape(img, draw, track, artist, album, art_url, is_playing,
                       width, height, dark, text_main, text_sub):
    pad = max(12, height // 20)
    art_size = height - pad * 2
    art = _fetch_art(art_url, (art_size, art_size)) or _placeholder_art((art_size, art_size))
    img.paste(art, (pad, pad))

    if not is_playing:
        overlay = Image.new("RGBA", (art_size, art_size), IDLE_OVERLAY)
        img.paste(overlay, (pad, pad), overlay)

    text_x = pad + art_size + pad
    text_w = width - text_x - pad
    if text_w < 40:
        return

    # Last.fm badge
    badge_font = _find_font(max(9, height // 28))
    badge_text = "LAST.FM" if is_playing else "LAST.FM  ·  LAST PLAYED"
    draw.text((text_x, pad), badge_text, fill=LASTFM_RED, font=badge_font)
    badge_h = draw.textbbox((0, 0), badge_text, font=badge_font)[3]

    # Track name
    track_font_sz = max(14, height // 7)
    track_font    = _find_font(track_font_sz, bold=True)
    track_y       = pad + badge_h + pad // 2
    track_lines   = _wrap_text(track, track_font, text_w, draw)[:2]
    for line in track_lines:
        draw.text((text_x, track_y), line, fill=text_main, font=track_font)
        track_y += draw.textbbox((0, 0), line, font=track_font)[3] + 4

    # Artist
    artist_font_sz = max(11, height // 10)
    artist_font    = _find_font(artist_font_sz)
    track_y       += pad // 3
    draw.text((text_x, track_y), artist, fill=text_main, font=artist_font)
    track_y += draw.textbbox((0, 0), artist, font=artist_font)[3] + 6

    # Album
    album_font = _find_font(max(9, height // 13))
    album_lines = _wrap_text(album, album_font, text_w, draw)[:1]
    for line in album_lines:
        draw.text((text_x, track_y), line, fill=text_sub, font=album_font)


def _render_portrait(img, draw, track, artist, album, art_url, is_playing,
                      width, height, dark, text_main, text_sub):
    pad      = max(12, width // 20)
    art_size = width - pad * 2
    art_top  = pad
    art      = _fetch_art(art_url, (art_size, art_size)) or _placeholder_art((art_size, art_size))
    img.paste(art, (pad, art_top))

    if not is_playing:
        overlay = Image.new("RGBA", (art_size, art_size), IDLE_OVERLAY)
        img.paste(overlay, (pad, art_top), overlay)

    text_y = art_top + art_size + pad

    badge_font = _find_font(max(9, width // 22))
    badge_text = "LAST.FM" if is_playing else "LAST.FM  ·  LAST PLAYED"
    draw.text((pad, text_y), badge_text, fill=LASTFM_RED, font=badge_font)
    text_y += draw.textbbox((0, 0), badge_text, font=badge_font)[3] + pad // 2

    track_font = _find_font(max(13, width // 9), bold=True)
    for line in _wrap_text(track, track_font, width - pad * 2, draw)[:3]:
        draw.text((pad, text_y), line, fill=text_main, font=track_font)
        text_y += draw.textbbox((0, 0), line, font=track_font)[3] + 4

    text_y += pad // 3
    artist_font = _find_font(max(10, width // 12))
    draw.text((pad, text_y), artist, fill=text_main, font=artist_font)
    text_y += draw.textbbox((0, 0), artist, font=artist_font)[3] + 6

    album_font = _find_font(max(9, width // 14))
    for line in _wrap_text(album, album_font, width - pad * 2, draw)[:1]:
        draw.text((pad, text_y), line, fill=text_sub, font=album_font)


def _render_square(img, draw, track, artist, album, art_url, is_playing,
                    width, height, dark, text_main, text_sub):
    # Full-bleed art with dark gradient overlay + text at bottom
    art = _fetch_art(art_url, (width, height)) or _placeholder_art((width, height))
    if not is_playing:
        art = art.filter(ImageFilter.GaussianBlur(radius=3))
    img.paste(art, (0, 0))

    # Gradient overlay at bottom third
    grad_h = height // 2
    gradient = Image.new("RGBA", (width, grad_h), (0, 0, 0, 0))
    for y in range(grad_h):
        alpha = int(220 * (y / grad_h))
        ImageDraw.Draw(gradient).line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    img.paste(Image.new("RGB", (width, grad_h), (0, 0, 0)), (0, height - grad_h), gradient)

    draw = ImageDraw.Draw(img)
    pad = max(10, width // 24)
    text_y = height - pad

    album_font = _find_font(max(9, width // 22))
    album_text = album[:40]
    draw.text((pad, text_y), album_text, fill=TEXT_GRAY_D, font=album_font, anchor="ls")
    text_y -= draw.textbbox((0, 0), album_text, font=album_font)[3] + 6

    artist_font = _find_font(max(11, width // 16))
    draw.text((pad, text_y), artist, fill=TEXT_GRAY_D, font=artist_font, anchor="ls")
    text_y -= draw.textbbox((0, 0), artist, font=artist_font)[3] + 8

    track_font = _find_font(max(13, width // 12), bold=True)
    for line in reversed(_wrap_text(track, track_font, width - pad * 2, draw)[:2]):
        draw.text((pad, text_y), line, fill=TEXT_WHITE, font=track_font, anchor="ls")
        text_y -= draw.textbbox((0, 0), line, font=track_font)[3] + 4

    badge_font = _find_font(max(8, width // 28))
    badge = "LAST.FM" if is_playing else "LAST.FM  ·  LAST PLAYED"
    draw.text((pad, text_y - 6), badge, fill=LASTFM_RED, font=badge_font, anchor="ls")
