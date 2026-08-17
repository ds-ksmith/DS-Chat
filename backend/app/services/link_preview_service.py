import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import LinkPreview
from app.services.ssrf import UnsafeUrlError, validate_target_url
from app.ws.broadcaster import Broadcaster

logger = logging.getLogger(__name__)

# Deliberately not a full URL regex (e.g. no IPv6-literal-host support) --
# just enough to find "a URL-shaped thing" in a chat message the same way
# the frontend's Markdown renderer autolinks bare URLs. Trailing punctuation
# a sentence would naturally have after a URL (a period, closing paren from
# "(see https://example.com)", etc.) is trimmed off separately below.
_URL_RE = re.compile(r"https?://[^\s<>\"]+")
_TRAILING_PUNCTUATION = ".,;:!?)'\">"

_FETCH_TIMEOUT_SECONDS = 5.0
_MAX_BYTES = 512 * 1024
_MAX_REDIRECTS = 3
_USER_AGENT = "ds-chat-link-preview/1.0"
_CACHE_TTL = timedelta(days=7)


def extract_first_url(content: str | None) -> str | None:
    if not content:
        return None
    match = _URL_RE.search(content)
    if not match:
        return None
    return match.group(0).rstrip(_TRAILING_PUNCTUATION) or None


class _OpenGraphParser(HTMLParser):
    """Pulls og:title/og:description/og:image/og:site_name meta tags,
    falling back to <title> -- stdlib html.parser is enough for meta-tag
    scraping, no reason to add a full HTML parsing dependency (e.g.
    BeautifulSoup) just for this."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.og: dict[str, str] = {}
        self.title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            attr_dict = dict(attrs)
            prop = attr_dict.get("property") or attr_dict.get("name")
            content = attr_dict.get("content")
            if prop and content and prop.startswith("og:"):
                self.og.setdefault(prop, content)
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is None:
            self.title = data.strip()


async def _fetch_preview_data(url: str) -> dict | None:
    """SSRF-safe fetch: validates (scheme + resolved-IP allowlist check,
    see ssrf.py) before *every* hop, following redirects manually rather
    than via httpx's own follow_redirects -- that would connect to each
    intermediate hop before any of them got validated, defeating the point.
    Still subject to the DNS-rebinding gap documented in ssrf.py (a window
    between validating a hostname and httpx independently resolving it to
    connect); accepted for the same reason it's accepted there.
    """
    current_url = url
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_SECONDS, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            try:
                validate_target_url(current_url)
            except UnsafeUrlError:
                return None

            try:
                async with client.stream(
                    "GET", current_url, headers={"User-Agent": _USER_AGENT}
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current_url = str(httpx.URL(current_url).join(location))
                        continue
                    if response.status_code >= 400:
                        return None
                    content_type = response.headers.get("content-type", "")
                    if "text/html" not in content_type:
                        return None
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) >= _MAX_BYTES:
                            break
                    break
            except httpx.HTTPError:
                return None
        else:
            return None

    parser = _OpenGraphParser()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
    except Exception:
        return None

    title = parser.og.get("og:title") or parser.title
    if not title:
        return None

    return {
        "title": title.strip()[:500],
        "description": (parser.og.get("og:description") or "").strip()[:1000] or None,
        "image_url": parser.og.get("og:image") or None,
        "site_name": (parser.og.get("og:site_name") or "").strip()[:200] or None,
    }


async def _get_or_fetch(db: AsyncSession, url: str) -> LinkPreview | None:
    """Returns None only when there's genuinely nothing to show (a fresh
    fetch failed, or a cached row says an earlier one did) -- callers don't
    need to distinguish "still fetching" from "never going to have one"."""
    existing = (await db.execute(select(LinkPreview).where(LinkPreview.url == url))).scalar_one_or_none()

    if existing is not None and datetime.now(timezone.utc) - existing.fetched_at < _CACHE_TTL:
        return None if existing.fetch_failed else existing

    data = await _fetch_preview_data(url)
    if existing is not None:
        existing.fetch_failed = data is None
        if data:
            existing.title = data["title"]
            existing.description = data["description"]
            existing.image_url = data["image_url"]
            existing.site_name = data["site_name"]
        existing.fetched_at = datetime.now(timezone.utc)
        await db.commit()
        return None if data is None else existing

    row = LinkPreview(
        url=url,
        fetch_failed=data is None,
        **(data or {"title": None, "description": None, "image_url": None, "site_name": None}),
    )
    db.add(row)
    await db.commit()
    return None if data is None else row


async def fetch_and_broadcast_link_preview(
    broadcaster: Broadcaster, room_id: uuid.UUID, message_id: uuid.UUID, url: str
) -> None:
    """Entry point for a fire-and-forget asyncio.create_task from
    broadcast_new_message -- runs on its own DB session (see push_service.py's
    send_push_to_user docstring for why a background task must never share
    the caller's session) so a slow/hanging fetch can never delay message
    delivery to anyone actually online.
    """
    try:
        async with async_session_factory() as db:
            preview = await _get_or_fetch(db, url)
    except Exception:
        logger.warning("Link preview fetch failed for %s", url, exc_info=True)
        return

    if preview is None:
        return

    await broadcaster.publish(
        room_id,
        {
            "type": "link_preview",
            "room_id": str(room_id),
            "id": str(message_id),
            "url": preview.url,
            "title": preview.title,
            "description": preview.description,
            "image_url": preview.image_url,
            "site_name": preview.site_name,
        },
    )


async def get_link_previews_for_urls(db: AsyncSession, urls: list[str]) -> dict[str, LinkPreview]:
    """Batch lookup for message history -- mirrors message_service.
    get_reactions_for_messages's shape (one query, zipped back onto results
    by the caller) rather than an ORM relationship, since the join key is a
    plain string column, not a FK."""
    if not urls:
        return {}
    result = await db.execute(select(LinkPreview).where(LinkPreview.url.in_(urls), LinkPreview.fetch_failed.is_(False)))
    return {row.url: row for row in result.scalars().all()}
