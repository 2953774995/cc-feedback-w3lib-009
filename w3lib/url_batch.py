"""Batch URL normalization and deduplication helpers.

Built on top of :func:`w3lib.url.canonicalize_url` for the common crawling
pipeline case: a daily batch of collected links that must be normalized,
deduplicated, and reconciled (which inputs were merged, which were dropped
as invalid) in one pass, without a single bad link aborting the batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from w3lib.url import canonicalize_url

# Default ports that carry no information and are stripped during
# normalization (http://example.com:80/ == http://example.com/).
_DEFAULT_PORTS = {"http": 80, "https": 443}

# Query parameter names that only serve tracking purposes. Anything with a
# ``utm_`` prefix counts, plus a handful of well-known click-id parameters.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_NAMES = frozenset(
    {
        "gclid",
        "dclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "_ga",
    }
)


@dataclass
class NormalizeResult:
    """Outcome of :func:`normalize_many`.

    .. attribute:: unique

        Canonicalized URLs, deduplicated, in first-seen order.

    .. attribute:: duplicates

        Mapping of canonical URL -> list of original inputs that were
        merged into an earlier entry. Only canonical URLs that actually
        had duplicates appear as keys.

    .. attribute:: invalid

        Original inputs that could not be parsed as URLs, in input order.
    """

    unique: list[str] = field(default_factory=list)
    duplicates: dict[str, list[Any]] = field(default_factory=dict)
    invalid: list[Any] = field(default_factory=list)


def _is_tracking_param(name: str) -> bool:
    if name in _TRACKING_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in _TRACKING_PREFIXES)


def _normalize_one(url: Any, drop_tracking: bool) -> str:
    """Canonicalize a single URL or raise ``ValueError``/``TypeError``."""
    if isinstance(url, bytes):
        url = url.decode("utf8")
    if not isinstance(url, str):
        raise TypeError(f"expected str or bytes, got {type(url).__name__}")

    # urlsplit raises ValueError for malformed ports, IPv6 literals, etc.
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if not scheme or not parts.netloc:
        raise ValueError(f"not an absolute URL: {url!r}")
    host = parts.hostname
    if not host:
        raise ValueError(f"URL without a host: {url!r}")
    port = parts.port  # raises ValueError on an out-of-range/invalid port

    # Rebuild the netloc, preserving userinfo and dropping default ports.
    userinfo = ""
    if "@" in parts.netloc:
        userinfo = parts.netloc.rsplit("@", 1)[0] + "@"
    host_part = f"[{host}]" if ":" in host else host
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{userinfo}{host_part}:{port}"
    else:
        netloc = f"{userinfo}{host_part}"

    query = parts.query
    if drop_tracking and query:
        # Filter on the raw pairs to avoid re-encoding surprises; the
        # canonicalize_url() call below re-parses and sorts what remains.
        kept = [
            pair
            for pair in query.split("&")
            if not _is_tracking_param(pair.split("=", 1)[0])
        ]
        query = "&".join(kept)

    # Fragments never reach the canonical form: the same document with and
    # without ``#frag`` is the same entry for dedup purposes.
    stripped = urlunsplit((scheme, netloc, parts.path, query, ""))
    return canonicalize_url(stripped, keep_fragments=False)


def normalize_many(urls: Iterable[Any], drop_tracking: bool = True) -> NormalizeResult:
    """Normalize and deduplicate a batch of URLs.

    Each input is canonicalized with :func:`w3lib.url.canonicalize_url`
    after lowercasing the scheme, stripping default ports and (unless
    ``drop_tracking=False``) removing tracking query parameters such as
    ``utm_*``. Fragments are dropped so that ``#frag`` variants of the same
    document deduplicate together.

    Deduplication compares canonical forms; the first occurrence wins and
    later originals are recorded in ``result.duplicates``. Inputs that
    cannot be parsed land in ``result.invalid`` without aborting the batch.
    """
    result = NormalizeResult()
    seen: set[str] = set()
    for url in urls:
        try:
            canonical = _normalize_one(url, drop_tracking=drop_tracking)
        except (ValueError, TypeError):
            result.invalid.append(url)
            continue
        if canonical in seen:
            result.duplicates.setdefault(canonical, []).append(url)
        else:
            seen.add(canonical)
            result.unique.append(canonical)
    return result
