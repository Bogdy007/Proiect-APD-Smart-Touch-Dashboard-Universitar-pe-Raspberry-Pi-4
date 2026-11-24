"""Teste unitare pentru CacheScheduler și logica de exponential backoff."""

from __future__ import annotations

import asyncio
import random

from src.backend.interfaces import SourceError
from src.backend.schemas import (
    EmailDetail,
    NewsItem,
    NewsSource,
    WeatherCondition,
    WeatherCurrent,
    WeatherData,
)
from src.cache.cache_manager import SQLiteCacheManager, SQLiteConfigStore, SQLiteDatabase
from src.cache.scheduler import CacheScheduler, compute_backoff_delay


def test_compute_backoff_exponential_cap_jitter_and_retry_after():
    rng = random.Random(42)

    # Fără jitter: verificare exactă min(base * 2^n, 900)
    assert compute_backoff_delay(1, base_s=15.0, max_s=900.0, jitter_ratio=0.0) == 30.0
    assert compute_backoff_delay(2, base_s=15.0, max_s=900.0, jitter_ratio=0.0) == 60.0
    assert compute_backoff_delay(5, base_s=15.0, max_s=900.0, jitter_ratio=0.0) == 480.0
    assert compute_backoff_delay(10, base_s=15.0, max_s=900.0, jitter_ratio=0.0) == 900.0

    # Cu jitter ±20% rămâne în intervalul [0.8 * raw, min(1.2 * raw, max_s)]
    d = compute_backoff_delay(2, base_s=15.0, max_s=900.0, jitter_ratio=0.2, rng=rng)
    assert 48.0 <= d <= 72.0

    # Respectă retry_after_s (HTTP 429) când depășește backoff-ul calculat
    d_429 = compute_backoff_delay(1, base_s=15.0, max_s=900.0, retry_after_s=120.0, jitter_ratio=0.0)
    assert d_429 == 120.0


class _DummyMail:
    mode = "mock"

    async def fetch_inbox(self, limit: int = 50) -> list[EmailDetail]:
        return []


class _FlakyWeather:
    def __init__(self) -> None:
        self.fail = True
        self.calls = 0

    async def fetch(self, latitude: float, longitude: float, location_name: str) -> WeatherData:
        self.calls += 1
        if self.fail:
            raise SourceError("weather", "offline", retry_after_s=None)
        return WeatherData(
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
            current=WeatherCurrent(
                temperature_c=11.0,
                feels_like_c=9.5,
                humidity_pct=60,
                wind_kmh=8.0,
                condition=WeatherCondition.PARTLY_CLOUDY,
                description="Parțial noros",
            ),
        )


class _DummyNews:
    async def fetch(self, sources: list[NewsSource]) -> list[NewsItem]:
        return []


def test_scheduler_runs_handles_failure_and_recovers_on_connectivity(tmp_path):
    async def _run():
        db = SQLiteDatabase(tmp_path / "sched.db")
        config = SQLiteConfigStore(db)
        weather = _FlakyWeather()
        cache = SQLiteCacheManager(
            config,
            db,
            mail_provider=_DummyMail(),
            weather_provider=weather,
            news_provider=_DummyNews(),
        )
        updated_widgets: list[str] = []

        async def _on_update(widget: str) -> None:
            updated_widgets.append(widget)

        scheduler = CacheScheduler(
            cache,
            config,
            on_data_updated=_on_update,
            backoff_base_s=5.0,
            backoff_max_s=60.0,
            jitter_ratio=0.0,
            run_immediately=True,
        )

        await scheduler.start()
        assert scheduler.is_running is True
        await asyncio.sleep(0.15)

        # email și news au reușit și au notificat callback-ul; weather a eșuat (backoff activ)
        assert "email" in updated_widgets
        assert "news" in updated_widgets
        assert scheduler.get_state("weather").consecutive_failures >= 1
        assert scheduler.get_state("weather").last_error is not None

        # Rețeaua revine -> on_connectivity_restored trezește imediat bucla fără să aștepte backoff-ul
        weather.fail = False
        await scheduler.on_connectivity_restored()
        await asyncio.sleep(0.15)

        assert scheduler.get_state("weather").consecutive_failures == 0
        assert "weather" in updated_widgets
        env = await cache.get_weather()
        assert env.meta.is_stale is False
        assert env.data.current.temperature_c == 11.0

        await scheduler.stop()
        assert scheduler.is_running is False
        await cache.aclose()
        db.close()

    asyncio.run(_run())