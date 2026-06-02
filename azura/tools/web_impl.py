"""Concrete web tool implementations: DDG search + safe URL fetch."""
from __future__ import annotations

import html
import re
from urllib.parse import quote_plus, urlparse

import httpx

from azura.config import get_settings
from azura.telegram.media_dl import _is_private_ip
from azura.utils.log import get_logger

log = get_logger("tools.web")

_RESULT_RE = re.compile(
    r"<a[^>]+class=\"result__a\"[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>.*?"
    r"class=\"result__snippet\"[^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip(s: str) -> str:
    return html.unescape(_TAG_RE.sub("", s or "")).strip()


async def ddg_search(query: str) -> list[dict]:
    """Hit DuckDuckGo html endpoint and parse top results."""
    s = get_settings()
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    async with httpx.AsyncClient(timeout=s.web_fetch_timeout_s, follow_redirects=True,
                                 headers={"user-agent": "Mozilla/5.0"}) as cli:
        r = await cli.get(url)
        r.raise_for_status()
        body = r.text
    out: list[dict] = []
    for m in _RESULT_RE.finditer(body):
        href = html.unescape(m.group(1))
        title = _strip(m.group(2))
        snippet = _strip(m.group(3))
        if not href.startswith("http"):
            continue
        out.append({"url": href, "title": title, "snippet": snippet})
        if len(out) >= 10:
            break
    return out


async def fetch_text(url: str) -> str:
    """Fetch a URL and return a stripped text body, with SSRF + size guard."""
    s = get_settings()
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(f"scheme not allowed: {p.scheme}")
    host = p.hostname or ""
    if not host or _is_private_ip(host):
        raise ValueError("host blocked")
    async with httpx.AsyncClient(timeout=s.web_fetch_timeout_s, follow_redirects=True,
                                 headers={"user-agent": "Mozilla/5.0"}) as cli:
        r = await cli.get(url)
        r.raise_for_status()
        body = r.text[: 200 * 1024]
    return _strip(body)
