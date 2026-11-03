"""Domain models for aggregated news items."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from app.normalization import normalize_text

#: Minimum Jaccard similarity of two titles' token sets to count as the same news.
#: Tuned to be conservative: a missed merge (visible duplicate) is less harmful
#: than a wrong one (a distinct article silently dropped).
TITLE_SIMILARITY_THRESHOLD = 0.65

#: Word tokens; ``.``/``_``/``-`` inside a word are kept, so ``gpt-5.2`` stays
#: one token and version numbers remain distinguishable. ``[^\W_]`` is letters
#: and digits without underscore — works for any language, not just ASCII.
_TITLE_TOKEN_RE = re.compile(r"[^\W_]+(?:[._-][^\W_]+)*")


@dataclass(frozen=True)
class NewsItem:
    """A single news article or post as fetched from a source."""

    title: str
    url: str
    source: str
    published_at: datetime | None = None
    summary: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def normalize_url(url: str) -> str:
    """Normalize a URL for dedup: lowercase scheme/host, drop fragment and trailing slash.

    The result is stored in ``articles.normalized_url`` and guarded by a unique
    index, so it is the canonical dedup key across sources.
    """
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def compute_content_hash(title: str, content: str) -> str | None:
    """sha256 of the normalized title and content — dedup key across different URLs.

    Catches the same material syndicated under a new URL: the URL key cannot see
    it, but identical title+content can. Returns ``None`` when ``content`` is
    empty — a title alone is too weak a signal (generic titles collide across
    genuinely different articles), so such items are deduplicated by URL only.
    NULLs never conflict in a unique index, so the guard needs no special case.
    """
    title = normalize_text(title)
    content = normalize_text(content)
    if not content:
        return None
    return hashlib.sha256(f"{title}\n{content}".encode()).hexdigest()


def _title_tokens(title: str) -> frozenset[str]:
    """Casefolded word tokens of a title; order and punctuation do not matter."""
    return frozenset(_TITLE_TOKEN_RE.findall(title.casefold()))


def _number_tokens(tokens: frozenset[str]) -> frozenset[str]:
    """Tokens containing digits — strong distinguishing signals in headlines."""
    return {token for token in tokens if any(ch.isdigit() for ch in token)}


def titles_similar(left: str, right: str, threshold: float = TITLE_SIMILARITY_THRESHOLD) -> bool:
    """True when two titles likely describe the same news item.

    Titles are tokenized (casefolded, split on punctuation, words kept whole)
    and compared with Jaccard similarity of the token sets, so word order,
    casing, punctuation and a trailing ``| Publisher`` suffix do not matter.

    Two guards keep precision up:

    * different numbers -> never similar (``GPT-5`` vs ``GPT-5.2``,
      ``Top 10`` vs ``Top 5`` are different news);
    * an empty token set on either side -> never similar (no signal to judge by).

    Used by the aggregator before anything is saved: similarity is not
    transitive, so it cannot be a DB unique index — the database keeps enforcing
    the exact keys (``normalized_url``, ``content_hash``) instead.
    """
    left_tokens = _title_tokens(left)
    right_tokens = _title_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if _number_tokens(left_tokens) != _number_tokens(right_tokens):
        return False
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= threshold
