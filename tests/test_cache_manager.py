"""Teste unitare și de integrare pentru SQLiteConfigStore și SQLiteCacheManager."""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.backend import interfaces
from src.backend.app import Services, create_app
from src.backend.interfaces import SourceError
from src.backend.mock_services import MockAuthService, MockMetricsProvider
from src.backend.schemas import (
    DataSource,
    EmailDetail,
    EmailFilter,
    NewsItem,
    NewsSource,
    NewsSourceCreate,
    NewsSourceUpdate,
    WeatherCondition,
    WeatherCurrent,
    WeatherData,
)
from src.cache.cache_manager import SQLiteCacheManager, SQLiteConfigStore, SQLiteDatabase


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FakeMailProvider:
    mode = "mock"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def fetch_inbox(self, limit: int = 50) -> list[EmailDetail]:
        self.calls += 1
        if self.fail:
            raise SourceError("email", "timeout simulat")
        now = _now()
        return [
            EmailDetail(
                id="mail-1",
                sender_name="Secretariat",
                sender_address="sec@unitbv.ro",
                subject="Orar examene",
                preview="Text previzualizare curat.",
                received_at=now - timedelta(minutes=5),
                is_read=False,
                is_priority=True,
            ),
            EmailDetail(
                id="mail-2",
                sender_name="Biblioteca",
                sender_address="bib@unitbv.ro",
                subject="Program vacanță",
                preview="Biblioteca este deschisă.",
                received_at=now - timedelta(hours=2),
                is_read=True,
                is_priority=False,
            ),
        ][:limit]


class FakeWeatherProvider:
    def __init__(self, fail: bool = False, retry_after_s: float | None = None) -> None:
        self.fail = fail
        self.retry_after_s = retry_after_s
        self.calls = 0

    async def fetch(self, latitude: float, longitude: float, location_name: str) -> WeatherData:
        self.calls += 1
        if self.fail:
            raise SourceError("weather", "HTTP 429 rate limit", retry_after_s=self.retry_after_s)
        return WeatherData(
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
            current=WeatherCurrent(
                temperature_c=9.5,
                feels_like_c=7.0,
                humidity_pct=65,
                wind_kmh=10.0,
                condition=WeatherCondition.CLEAR,
                description="Senin",
            ),
        )


class FakeNewsProvider:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def fetch(self, sources: list[NewsSource]) -> list[NewsItem]:
        self.calls += 1
        if self.fail:
            raise SourceError("news", "HTTP 500 server error")
        now = _now()
        return [
            NewsItem(
                id=f"news-{s.id}-1",
                source_id=s.id,
                source_name=s.name,
                title=f"Știre de la {s.name}",
                summary="Rezumat curățat.",
                link=f"https://example.com/{s.id}/1",
                published_at=now - timedelta(minutes=10),
            )
            for s in sources
        ]


def test_async_protocol_compliance():
    """Verifică că toate metodele din CacheService și ConfigStore sunt async def."""
    for impl, proto in (
        (SQLiteCacheManager, interfaces.CacheService),
        (SQLiteConfigStore, interfaces.ConfigStore),
    ):
        proto_methods = [
            name for name, val in vars(proto).items()
            if inspect.isfunction(val) and not name.startswith("_")
        ]
        sync = [m for m in proto_methods if not inspect.iscoroutinefunction(getattr(impl, m))]
        assert not sync, f"{impl.__name__} are metode sincrone: {sync}"


def test_config_store_persists_across_restarts(tmp_path):
    db_file = tmp_path / "cache.db"

    async def _run():
        store1 = SQLiteConfigStore(db_file)
        cfg = await store1.get_config()
        assert len(cfg.widgets) == 4
        cfg.widgets[0].enabled = False
        cfg.auto_lock_minutes = 10
        await store1.save_config(cfg)

        added = await store1.add_news_source(
            NewsSourceCreate(name="Tech", url="https://example.com/tech.xml")
        )
        updated = await store1.update_news_source(added.id, NewsSourceUpdate(enabled=False))
        assert updated is not None and updated.enabled is False
        store1.close()

        # Redeschidem baza de date (simulează repornirea Raspberry Pi)
        store2 = SQLiteConfigStore(db_file)
        reloaded = await store2.get_config()
        assert reloaded.widgets[0].enabled is False
        assert reloaded.auto_lock_minutes == 10
        sources = await store2.list_news_sources()
        assert any(s.id == added.id and not s.enabled for s in sources)
        assert await store2.delete_news_source(added.id) is True
        assert await store2.delete_news_source(added.id) is False
        store2.close()

    asyncio.run(_run())


def test_ttl_expiration_and_offline_fallback(tmp_path):
    """Verifică expirarea TTL-ului, fallback-ul offline cu is_stale=True și reluarea sincronizării."""
    db_file = tmp_path / "cache.db"

    async def _run():
        db = SQLiteDatabase(db_file)
        config = SQLiteConfigStore(db)
        weather = FakeWeatherProvider(fail=False)
        cache = SQLiteCacheManager(
            config,
            db,
            weather_provider=weather,
            ttls={"weather": 1},
            min_manual_refresh_interval_s=0.0,
        )

        # 1. Prima cerere (cache miss -> fetch live)
        env1 = await cache.get_weather()
        assert env1.meta.is_stale is False
        assert env1.meta.source is DataSource.LIVE
        assert env1.data.current.temperature_c == 9.5
        assert weather.calls == 1

        # 2. A doua cerere imediată -> servită din cache (fără apel nou la sursă)
        env2 = await cache.get_weather()
        assert env2.meta.is_stale is False
        assert weather.calls == 1

        # 3. Simulăm căderea sursei și expirarea TTL-ului
        weather.fail = True
        weather.retry_after_s = 30.0
        await asyncio.sleep(1.1)

        env3 = await cache.get_weather()
        assert env3.meta.is_stale is True
        assert env3.meta.source is DataSource.CACHE
        assert env3.meta.age_seconds >= 1
        assert env3.data.current.temperature_c == 9.5

        # Așteptăm revalidarea din fundal și verificăm că eroarea și consecutive_failures sunt înregistrate
        await asyncio.sleep(0.05)
        res_fail = await cache.refresh_with_status("weather", force=True)
        assert res_fail.success is False
        assert res_fail.retry_after_s == 30.0

        tel = {t.source: t for t in await cache.get_telemetry()}
        assert tel["weather"].consecutive_failures >= 1
        assert tel["weather"].cache_hits >= 2
        assert tel["weather"].cache_misses == 1

        # 4. Sursa revine online -> refresh reușește, is_stale redevine False
        weather.fail = False
        res_ok = await cache.refresh_with_status("weather", force=True)
        assert res_ok.success is True
        env4 = await cache.get_weather()
        assert env4.meta.is_stale is False
        assert env4.meta.error is None

        await cache.aclose()
        db.close()

    asyncio.run(_run())


def test_cold_start_offline_returns_empty_stale_without_exceptions(tmp_path):
    """Scenariul T-15: prima pornire fără internet nu aruncă excepții."""
    db_file = tmp_path / "cold.db"

    async def _run():
        db = SQLiteDatabase(db_file)
        config = SQLiteConfigStore(db)
        cache = SQLiteCacheManager(
            config,
            db,
            mail_provider=FakeMailProvider(fail=True),
            weather_provider=FakeWeatherProvider(fail=True),
            news_provider=FakeNewsProvider(fail=True),
        )

        emails = await cache.get_emails(EmailFilter.ALL, 20)
        assert emails.data.items == []
        assert emails.data.unread_count == 0
        assert emails.meta.is_stale is True
        assert emails.meta.error is not None

        weather = await cache.get_weather()
        assert weather.data.current.condition is WeatherCondition.UNKNOWN
        assert weather.meta.is_stale is True

        news = await cache.get_news(None, 20)
        assert news.data.items == []
        assert news.meta.is_stale is True

        await cache.aclose()
        db.close()

    asyncio.run(_run())


def test_email_filtering_mark_read_and_no_preview_in_list(tmp_path):
    db_file = tmp_path / "mail.db"

    async def _run():
        db = SQLiteDatabase(db_file)
        config = SQLiteConfigStore(db)
        cache = SQLiteCacheManager(config, db, mail_provider=FakeMailProvider())

        all_env = await cache.get_emails(EmailFilter.ALL, 20)
        assert all_env.meta.source is DataSource.MOCK
        assert all_env.data.unread_count == 1
        assert all("preview" not in item.model_dump() for item in all_env.data.items)

        unread_env = await cache.get_emails(EmailFilter.UNREAD, 20)
        assert [e.id for e in unread_env.data.items] == ["mail-1"]

        detail = await cache.get_email("mail-1")
        assert detail is not None and detail.data.preview == "Text previzualizare curat."
        assert await cache.get_email("inexistent") is None

        await cache.mark_read("mail-1")
        after_read = await cache.get_emails(EmailFilter.UNREAD, 20)
        assert after_read.data.items == []
        assert after_read.data.unread_count == 0

        await cache.aclose()
        db.close()

    asyncio.run(_run())


def test_integration_with_fastapi_app(tmp_path, monkeypatch):
    """Verifică integrarea reală a SQLiteCacheManager și SQLiteConfigStore în app.py."""
    monkeypatch.setenv("DASHBOARD_PIN", "4321")
    db = SQLiteDatabase(tmp_path / "api.db")
    config = SQLiteConfigStore(db)
    cache = SQLiteCacheManager(
        config,
        db,
        mail_provider=FakeMailProvider(),
        weather_provider=FakeWeatherProvider(),
        news_provider=FakeNewsProvider(),
    )
    app = create_app(
        Services(
            cache=cache,
            config=config,
            auth=MockAuthService(),
            metrics=MockMetricsProvider(),
            mail_mode="mock",
        )
    )

    try:
        with TestClient(app) as client:
            assert client.get("/api/weather").status_code == 200
            assert client.get("/api/news").status_code == 200
            mail_res = client.get("/api/email").json()
            assert len(mail_res["data"]["items"]) == 2
            assert all("preview" not in e for e in mail_res["data"]["items"])

            tel = client.get("/api/system/telemetry").json()
            assert len(tel["sources"]) == 3
    finally:
        asyncio.run(cache.aclose())
        db.close()