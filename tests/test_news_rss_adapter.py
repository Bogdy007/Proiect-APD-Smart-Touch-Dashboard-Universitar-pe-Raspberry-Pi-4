"""Teste unitare pentru RssNewsAdapter (src/adapters/news_rss_adapter.py).

Nu folosesc internetul: fluxurile RSS/Atom sunt simulate cu httpx.MockTransport.
"""

import asyncio

import httpx
import pytest

from src.adapters.news_rss_adapter import RssNewsAdapter, VERIFIED_FEEDS, clean_html
from src.backend.interfaces import SourceError
from src.backend.schemas import NewsItem, NewsSource


def _source(sid="s1", name="Sursa Test", url="https://example.com/feed.xml", enabled=True):
    return NewsSource(id=sid, name=name, url=url, enabled=enabled)


def _rss(items_xml: str, title="Feed Test") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>{title}</title><link>https://example.com</link>
{items_xml}</channel></rss>""".encode()


def _item(title, link, pub="Sun, 22 Nov 2026 10:00:00 +0000", desc="Sumar"):
    return f"""<item><title>{title}</title><link>{link}</link>
<pubDate>{pub}</pubDate><description>{desc}</description></item>"""


def _atom(entries_xml: str) -> bytes:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Feed</title>
{entries_xml}</feed>""".encode()


def _atom_entry(title, link, updated="2026-11-22T10:00:00Z", summary="Sumar atom"):
    return f"""<entry><title>{title}</title><link href="{link}"/>
<updated>{updated}</updated><summary>{summary}</summary></entry>"""


def _adapter(routes: dict[str, httpx.Response | Exception]) -> RssNewsAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for prefix, result in routes.items():
            if url.startswith(prefix):
                if isinstance(result, Exception):
                    raise result
                return result
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    return RssNewsAdapter(client=httpx.AsyncClient(transport=transport))


def _fetch(adapter, sources):
    return asyncio.run(adapter.fetch(sources))


GOOD_RSS = _rss(
    _item("Știre una", "https://example.com/a", desc="Primul sumar")
    + _item("Știre doi", "https://example.com/b", pub="Sun, 22 Nov 2026 09:00:00 +0000")
)


# ---------------------------------------------------------------------------
# Parsare RSS și Atom
# ---------------------------------------------------------------------------

def test_valid_rss_returns_news_items():
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=GOOD_RSS)})
    items = _fetch(adapter, [_source()])
    assert len(items) == 2
    first = items[0]  # ordonat descrescător după published_at
    assert first.title == "Știre una"
    assert first.source_id == "s1"
    assert first.source_name == "Sursa Test"
    assert first.summary == "Primul sumar"
    assert str(first.link) == "https://example.com/a"
    assert first.published_at.tzinfo is not None
    assert all(isinstance(i, NewsItem) for i in items)


def test_valid_atom_returns_news_items():
    body = _atom(
        _atom_entry("Articol Atom", "https://example.com/atom1")
        + _atom_entry("Alt Articol", "https://example.com/atom2", updated="2026-11-21T08:00:00Z")
    )
    adapter = _adapter({"https://atom.example.com/feed": httpx.Response(200, content=body)})
    src = _source(url="https://atom.example.com/feed")
    items = _fetch(adapter, [src])
    assert len(items) == 2
    assert items[0].title == "Articol Atom"


def test_multiple_sources_are_merged_and_sorted():
    routes = {
        "https://a.example.com/rss": httpx.Response(
            200, content=_rss(_item("De la A", "https://a.example.com/1", pub="Sun, 22 Nov 2026 12:00:00 +0000"))
        ),
        "https://b.example.com/rss": httpx.Response(
            200, content=_rss(_item("De la B", "https://b.example.com/1", pub="Sun, 22 Nov 2026 11:00:00 +0000"))
        ),
    }
    adapter = _adapter(routes)
    sources = [_source("a", "A", "https://a.example.com/rss"), _source("b", "B", "https://b.example.com/rss")]
    items = _fetch(adapter, sources)
    assert [i.source_id for i in items] == ["a", "b"]


def test_disabled_source_is_skipped():
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=GOOD_RSS)})
    items = _fetch(adapter, [_source(enabled=False)])
    assert items == []


# ---------------------------------------------------------------------------
# Curățarea HTML
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("<p>Text <b>bold</b></p>", "Text bold"),
        ("<script>alert(1)</script>Sigur", "Sigur"),
        ("<style>body{color:red}</style>Conținut", "Conținut"),
        ("<p>a</p><script>bad()</script><p>b</p>", "a b"),
        ("&lt;script&gt;alert(1)&lt;/script&gt;", "<script>alert(1)</script>"),  # entități -> text, nu executabil
        ("   spații   multiple\n\n", "spații multiple"),
        (None, ""),
        ("", ""),
    ],
)
def test_clean_html(raw, expected):
    assert clean_html(raw) == expected


def test_summary_strips_html_and_scripts():
    body = _rss(_item(
        "Titlu",
        "https://example.com/x",
        desc="<p>Informație <b>importantă</b></p><script>evil()</script>",
    ))
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=body)})
    items = _fetch(adapter, [_source()])
    assert items[0].summary == "Informație importantă"
    assert "<" not in items[0].summary and ">" not in items[0].summary


def test_summary_truncated_to_600_chars():
    long_text = "a" * 1000
    body = _rss(_item("Titlu", "https://example.com/long", desc=f"<p>{long_text}</p>"))
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=body)})
    items = _fetch(adapter, [_source()])
    assert len(items[0].summary) <= 600


# ---------------------------------------------------------------------------
# Deduplicare și sortare
# ---------------------------------------------------------------------------

def test_deduplication_by_link():
    dup = _item("Același link", "https://example.com/dup", pub="Sun, 22 Nov 2026 08:00:00 +0000")
    body = _rss(
        _item("Primul", "https://example.com/dup", pub="Sun, 22 Nov 2026 10:00:00 +0000")
        + dup
        + _item("Altul", "https://example.com/other", pub="Sun, 22 Nov 2026 09:00:00 +0000")
    )
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=body)})
    items = _fetch(adapter, [_source()])
    links = [str(i.link) for i in items]
    assert links.count("https://example.com/dup") == 1
    assert len(items) == 2


def test_deduplication_across_sources_keeps_newest():
    shared_link = "https://shared.example.com/story"
    old = _rss(_item("Versiune veche", shared_link, pub="Sun, 22 Nov 2026 08:00:00 +0000"))
    new = _rss(_item("Versiune nouă", shared_link, pub="Sun, 22 Nov 2026 11:00:00 +0000"))
    adapter = _adapter({
        "https://a.example.com/rss": httpx.Response(200, content=old),
        "https://b.example.com/rss": httpx.Response(200, content=new),
    })
    sources = [_source("a", "A", "https://a.example.com/rss"), _source("b", "B", "https://b.example.com/rss")]
    items = _fetch(adapter, sources)
    assert len(items) == 1
    assert items[0].title == "Versiune nouă"


def test_items_sorted_descending_by_date():
    body = _rss(
        _item("Vechi", "https://example.com/1", pub="Sun, 22 Nov 2026 08:00:00 +0000")
        + _item("Nou", "https://example.com/2", pub="Sun, 22 Nov 2026 12:00:00 +0000")
        + _item("Mediu", "https://example.com/3", pub="Sun, 22 Nov 2026 10:00:00 +0000")
    )
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=body)})
    items = _fetch(adapter, [_source()])
    titles = [i.title for i in items]
    assert titles == ["Nou", "Mediu", "Vechi"]


def test_item_id_is_stable_sha1_of_link():
    import hashlib
    body = _rss(_item("Titlu", "https://example.com/stabil"))
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=body)})
    item = _fetch(adapter, [_source()])[0]
    assert item.id == hashlib.sha1(b"https://example.com/stabil").hexdigest()


# ---------------------------------------------------------------------------
# Câmpuri lipsă / intrări invalide
# ---------------------------------------------------------------------------

def test_entries_without_link_or_date_are_skipped():
    body = _rss(
        "<item><title>Fără link</title><pubDate>Sun, 22 Nov 2026 10:00:00 +0000</pubDate></item>"
        + "<item><title>Fără dată</title><link>https://example.com/nodate</link></item>"
        + "<item><link>https://example.com/notitle</link><pubDate>Sun, 22 Nov 2026 10:00:00 +0000</pubDate></item>"
        + _item("Valid", "https://example.com/valid")
    )
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=body)})
    items = _fetch(adapter, [_source()])
    assert [i.title for i in items] == ["Valid"]


def test_empty_feed_returns_empty_list():
    body = _rss("")
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=body)})
    assert _fetch(adapter, [_source()]) == []


# ---------------------------------------------------------------------------
# Erori
# ---------------------------------------------------------------------------

def test_broken_xml_raises_source_error_when_all_sources_fail():
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=b"<rss><channel><item>")})
    with pytest.raises(SourceError):
        _fetch(adapter, [_source()])


def test_http_500_raises_source_error():
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(500, text="err")})
    with pytest.raises(SourceError):
        _fetch(adapter, [_source()])


def test_http_429_passes_retry_after():
    adapter = _adapter({
        "https://example.com/feed.xml": httpx.Response(429, headers={"Retry-After": "45"})
    })
    with pytest.raises(SourceError) as exc:
        _fetch(adapter, [_source()])
    assert exc.value.retry_after_s == 45.0


def test_timeout_raises_source_error():
    adapter = _adapter({"https://example.com/feed.xml": httpx.ReadTimeout("slow")})
    with pytest.raises(SourceError):
        _fetch(adapter, [_source()])


def test_unreachable_source_raises_source_error():
    adapter = _adapter({"https://example.com/feed.xml": httpx.ConnectError("down")})
    with pytest.raises(SourceError):
        _fetch(adapter, [_source()])


def test_html_instead_of_feed_raises_source_error():
    adapter = _adapter({"https://example.com/feed.xml": httpx.Response(200, content=b"<html><body>404 page</body></html>")})
    with pytest.raises(SourceError):
        _fetch(adapter, [_source()])


def test_partial_failure_returns_items_from_working_sources():
    adapter = _adapter({
        "https://ok.example.com/rss": httpx.Response(200, content=GOOD_RSS),
        "https://dead.example.com/rss": httpx.Response(503, text="down"),
    })
    sources = [_source("ok", "OK", "https://ok.example.com/rss"), _source("dead", "Dead", "https://dead.example.com/rss")]
    items = _fetch(adapter, sources)
    assert items and all(i.source_id == "ok" for i in items)


def test_invalid_url_source_is_reported():
    # NewsSource validează URL-ul la construcție; aici simulăm un URL care dă 404
    adapter = _adapter({})  # orice URL -> 404
    with pytest.raises(SourceError):
        _fetch(adapter, [_source(url="https://inexistent.example.com/rss")])


# ---------------------------------------------------------------------------
# Surse verificate (documentație pentru echipă)
# ---------------------------------------------------------------------------

def test_verified_feeds_are_well_formed():
    assert len(VERIFIED_FEEDS) >= 3
    for sid, name, url in VERIFIED_FEEDS:
        assert sid and name and url.startswith("https://")
