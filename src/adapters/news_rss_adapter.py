"""Adaptorul de știri DATA-WN: agregator RSS/Atom cu feedparser.

Implementează NewsProvider din src/backend/interfaces.py:

    async def fetch(sources: list[NewsSource]) -> list[NewsItem]

Pentru fiecare sursă activă descarcă fluxul cu httpx.AsyncClient (timeout
explicit, fără chei API), îl parsează cu feedparser (RSS 2.0 și Atom) și
normalizează articolele în NewsItem:
  - id = sha1(link) — stabil, pentru deduplicare
  - summary = text simplu, fără HTML/scripturi, maximum 600 caractere
  - deduplicare după link, ordonare descrescătoare după published_at (UTC)

La eșecul tuturor surselor ridică SourceError; dacă măcar o sursă merge,
întoarce știrile ei (erorile parțiale se loghează). Un flux valid, dar gol,
nenucontează ca eroare. Adaptorul nu face retry și nu cunoaște cache-ul.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import logging
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
from pydantic import HttpUrl, ValidationError

from src.backend.interfaces import SourceError
from src.backend.schemas import NewsItem, NewsSource

log = logging.getLogger(__name__)

SOURCE_NAME = "news"
DEFAULT_TIMEOUT_S = 10.0
SUMMARY_MAX_CHARS = 600
# Unele feed-uri (ex. phys.org) resping cererile fără User-Agent
USER_AGENT = "SmartTouchDashboard/1.0 (educational project; Raspberry Pi)"

# Elimină blocurile <script> și <style> înainte de a curăța tagurile
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Fluxuri RSS/Atom verificate (răspund 200 cu XML valid, noiembrie 2026).
# Pot fi folosite ca surse implicite în ConfigStore (CACHE).
VERIFIED_FEEDS: tuple[tuple[str, str, str], ...] = (
    # (id, nume, url)
    ("ars-technica", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("phys-org", "Phys.org", "https://phys.org/rss-feed/"),
    ("sciencedaily", "ScienceDaily", "https://www.sciencedaily.com/rss/all.xml"),
    ("unitbv-stiri", "UNITBV — Știri și evenimente",
     "https://unitbv.ro/?option=com_content&view=category&id=176&format=feed&type=rss"),
)


def _strip_markup(text: str) -> str:
    """Elimină blocurile script/style și toate tagurile HTML."""
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    return _TAG_RE.sub(" ", text)


def clean_html(raw: str | None) -> str:
    """Convertește conținutul HTML din RSS în text simplu sigur.

    Entitățile HTML pot fi codificate de mai multe ori (ex. `&amp;lt;`).
    De aceea facem două trepte de decodificare, fiecare urmată de eliminarea
    markup-ului: orice tag rezultat din decodificare e eliminat înainte să
    ajungă în output. Ce rămâne sunt exclusiv entități neverificabile ca
    markup — text inofensiv.
    """
    if not raw:
        return ""
    text = html.unescape(raw)
    text = _strip_markup(text)
    text = _strip_markup(html.unescape(text))
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    return text


def _parse_published(entry: dict[str, Any]) -> datetime | None:
    """Extrage published_at dintr-un entry feedparser, ca datetime UTC.

    Acceptă published_parsed / updated_parsed / dc:date. Intrările fără dată
    validă întorc None și sunt excluse (nu inventăm o dată).
    """
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed is None:
            # unele fluxuri pun data doar ca string — feedparser o parsează deja
            continue
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue

    for key in ("published", "updated", "created", "dc_date"):
        raw = entry.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            # RSS date format: "Sun, 22 Nov 2026 10:15:00 +0200"
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(raw)
            except (TypeError, ValueError):
                continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _entry_summary(entry: dict[str, Any]) -> str:
    """Alege cel mai bun câmp de sumar: content:encoded > summary > description."""
    content = entry.get("content")
    if isinstance(content, list) and content:
        value = content[0].get("value") if isinstance(content[0], dict) else None
        if value:
            return clean_html(str(value))
    return clean_html(entry.get("summary") or entry.get("description"))


def _entry_id(link: str) -> str:
    return hashlib.sha1(link.encode("utf-8")).hexdigest()


class RssNewsAdapter:
    """NewsProvider pe RSS/Atom cu feedparser.

    Parametri:
        client: httpx.AsyncClient opțional (injectabil în teste cu MockTransport).
        timeout_s: timeout explicit per request.
    """

    def __init__(self, client: httpx.AsyncClient | None = None, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._client = client
        self._timeout = httpx.Timeout(timeout_s)

    async def fetch(self, sources: list[NewsSource]) -> list[NewsItem]:
        active = [s for s in sources if s.enabled]
        if not active:
            return []

        async with self._maybe_client() as client:
            results = await asyncio.gather(
                *(self._fetch_source(client, source) for source in active),
                return_exceptions=True,
            )

        items: list[NewsItem] = []
        errors: list[str] = []
        for source, result in zip(active, results):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, SourceError):
                errors.append(str(result))
                log.warning("Sursa RSS '%s' a eșuat: %s", source.name, result)
            elif isinstance(result, BaseException):
                errors.append(f"{source.name}: {result!r}")
                log.warning("Eroare neașteptată la sursa '%s': %r", source.name, result)
            else:
                items.extend(result)

        # Nu ascundem erorile de rețea: dacă NICI o sursă nu a mers, ridicăm SourceError.
        # O singură sursă eșuată -> reluăm eroarea ei (păstrează retry_after_s la 429).
        if not items:
            if len(errors) == 1 and isinstance(results[0], SourceError):
                raise results[0]
            if errors:
                raise SourceError(SOURCE_NAME, "; ".join(errors))

        return self._deduplicate_and_sort(items)

    # ------------------------------------------------------------------
    # Descărcare și parsare per sursă
    # ------------------------------------------------------------------

    async def _fetch_source(self, client: httpx.AsyncClient, source: NewsSource) -> list[NewsItem]:
        url = str(source.url)
        try:
            response = await client.get(
                url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise SourceError(SOURCE_NAME, f"timeout la '{source.name}' ({url})") from e
        except httpx.HTTPStatusError as e:
            retry_after = self._retry_after_s(e.response)
            raise SourceError(
                SOURCE_NAME,
                f"HTTP {e.response.status_code} la '{source.name}' ({url})",
                retry_after_s=retry_after,
            ) from e
        except httpx.HTTPError as e:
            raise SourceError(SOURCE_NAME, f"eroare de rețea la '{source.name}': {e}") from e

        # feedparser e sincron; îl rulăm în thread ca să nu blocheze bucla de evenimente.
        # BytesIO e obligatoriu: altfel feedparser tratează bytes scurți ca
        # nume de fișier/cale locală și poate citi fișiere de pe disc.
        feed = await asyncio.to_thread(
            feedparser.parse, io.BytesIO(response.content)
        )

        if not feed.entries:
            # bozo = XML stricat; version gol = conținut care nu e deloc RSS/Atom (ex. HTML)
            if getattr(feed, "bozo", 0) and feed.bozo_exception:
                raise SourceError(
                    SOURCE_NAME,
                    f"flux invalid la '{source.name}': {feed.bozo_exception}",
                )
            if not getattr(feed, "version", ""):
                raise SourceError(
                    SOURCE_NAME,
                    f"'{source.name}' nu a returnat un flux RSS/Atom valid",
                )
            return []  # flux valid, dar fără articole

        items = []
        for entry in feed.entries:
            item = self._to_news_item(source, entry)
            if item is not None:
                items.append(item)

        # feedparser e iertător: poate extrage 'articole' din XML rupt.
        # Dacă bozo e setat și nu a rămas nimic valid, tratăm fluxul ca invalid.
        if not items and getattr(feed, "bozo", 0):
            raise SourceError(
                SOURCE_NAME,
                f"flux invalid la '{source.name}': {feed.bozo_exception}",
            )
        return items

    def _to_news_item(self, source: NewsSource, entry: Any) -> NewsItem | None:
        title = entry.get("title")
        link = entry.get("link")
        published_at = _parse_published(entry)

        # Nu generăm știri fictive: titlul, un link valid și o dată sunt obligatorii
        if not title or not link or published_at is None:
            return None

        try:
            link_url = HttpUrl(link)
        except ValidationError:
            return None

        return NewsItem(
            id=_entry_id(str(link_url)),
            source_id=source.id,
            source_name=source.name,
            title=clean_html(str(title)),
            summary=_entry_summary(entry),
            link=link_url,
            published_at=published_at,
        )

    @staticmethod
    def _deduplicate_and_sort(items: list[NewsItem]) -> list[NewsItem]:
        """Deduplicare după id (= sha1(link)); la link lipsă itemul a fost deja exclus.

        Păstrează apariția cu data cea mai nouă, apoi ordonează descrescător.
        """
        by_id: dict[str, NewsItem] = {}
        for item in items:
            existing = by_id.get(item.id)
            if existing is None or item.published_at > existing.published_at:
                by_id[item.id] = item
        return sorted(by_id.values(), key=lambda n: n.published_at, reverse=True)

    @staticmethod
    def _retry_after_s(response: httpx.Response) -> float | None:
        if response.status_code != 429:
            return None
        raw = response.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Gestionarea clientului httpx (injectabil pentru teste)
    # ------------------------------------------------------------------

    def _maybe_client(self):
        if self._client is not None:
            return _SharedClient(self._client)
        return httpx.AsyncClient(timeout=self._timeout)


class _SharedClient:
    """Context manager care NU închide un client injectat extern."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *exc) -> None:
        return None
