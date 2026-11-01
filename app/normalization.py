"""Data normalization: dates, encodings and plain-text conversion of HTML fields.

Applied at the source boundary (``RssSource``) and again defensively on save
(``storage``), so items are stored clean regardless of the source's quality.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from html import unescape

#: Inline and block-level tags, entities and markup noise.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
#: Zero-width characters and BOM leftovers that break search/dedup.
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")
#: C0/C1 control characters (except tab/newline, handled by whitespace collapse).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def clean_html(text: str | bytes | None) -> str:
    """Convert an HTML fragment to plain text: strip tags/script, unescape, collapse spaces."""
    text = normalize_text(text)
    if not text:
        return ""
    # Feeds often carry double-encoded HTML; unescape before stripping so that
    # escaped tags (e.g. "&lt;b&gt;") don't survive as literal markup.
    text = unescape(text)
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)


def normalize_text(value: str | bytes | bytearray | None) -> str:
    """Return clean ``str``: decode bytes (UTF-8, lossy), NFC-normalize, drop noise characters."""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", errors="replace")
    elif not isinstance(value, str):
        value = str(value)
    value = unicodedata.normalize("NFC", value)
    value = _ZERO_WIDTH_RE.sub("", value)
    value = _CONTROL_CHARS_RE.sub(" ", value)
    return _WS_RE.sub(" ", value).strip()


def normalize_datetime(dt: datetime | None) -> datetime | None:
    """Coerce to an aware UTC datetime; naive values are assumed to be UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
