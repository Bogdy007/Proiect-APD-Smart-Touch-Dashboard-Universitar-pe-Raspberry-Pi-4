"""Teste unitare pentru CacheScheduler, exponential backoff și tratarea HTTP 429."""

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

    def __init__(self) -> None:
        self.calls = 0

    async def fetch_inbox(self, limit: int = 50) -> list[EmailDetail]:
        self.calls += 1
        return []


class _FlakyWeather:
    def __init__(self, *, fail: bool = True, retry_after_s: float | None = None) -> None:
        self.fail = fail
        self.retry_after_s = retry_after_s
        self.calls = 0

    async def fetch(self, latitude: float, longitude: float, location_name: str) -> WeatherData:
        self.calls += 1
        if self.fail:
            raise SourceError("weather", "offline", retry_after_s=self.retry_after_s)
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


class _ScriptedWeather:
    """Execută o secvență fixă de erori (sau None pentru succes) la apelurile consecutive."""

    def __init__(self, script: list[SourceError | None]) -> None:
        self._script = list(script)
        self.calls = 0

    async def fetch(self, latitude: float, longitude: float, location_name: str) -> WeatherData:
        idx = self.calls
        self.calls += 1
        action = self._script[idx] if idx < len(self._script) else None
        if action is not None:
            raise action
        return WeatherData(
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
            current=WeatherCurrent(
                temperature_c=12.5,
                feels_like_c=10.0,
                humidity_pct=55,
                wind_kmh=6.0,
                condition=WeatherCondition.CLEAR,
                description="Senin",
            ),
        )


class _DummyNews:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, sources: list[NewsSource]) -> list[NewsItem]:
        self.calls += 1
        return []


def test_scheduler_runs_handles_failure_and_recovers_on_connectivity(tmp_path):
    async def _run():
        db = SQLiteDatabase(tmp_path / "sched.db")
        config = SQLiteConfigStore(db)
        weather = _FlakyWeather(fail=True)
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


def test_scheduler_exponential_backoff_after_consecutive_failures(tmp_path):
    """Verifică creșterea exponențială a backoff-ului la erori consecutive, plafonul și resetarea la succes."""
    async def _run():
        db = SQLiteDatabase(tmp_path / "backoff.db")
        config = SQLiteConfigStore(db)
        weather = _ScriptedWeather([
            SourceError("weather", "timeout #1"),
            SourceError("weather", "timeout #2"),
            SourceError("weather", "HTTP 500 #3"),
            SourceError("weather", "HTTP 503 #4"),
            None,  # a 5-a încercare reușește -> backoff se resetează
        ])
        cache = SQLiteCacheManager(
            config,
            db,
            mail_provider=_DummyMail(),
            weather_provider=weather,
            news_provider=_DummyNews(),
        )
        scheduler = CacheScheduler(
            cache,
            config,
            backoff_base_s=15.0,
            backoff_max_s=150.0,
            jitter_ratio=0.0,
            run_immediately=True,
        )

        weather_delays: list[float] = []
        observed_failures: list[int] = []

        async def _fake_wait(source, delay_s: float) -> bool:
            if source != "weather":
                return False
            weather_delays.append(delay_s)
            observed_failures.append(scheduler.get_state("weather").consecutive_failures)
            await asyncio.sleep(0)
            return len(weather_delays) < 5

        scheduler._wait_interruptible = _fake_wait  # type: ignore[method-assign]

        await scheduler.start()
        await asyncio.wait_for(asyncio.gather(*scheduler._tasks.values()), timeout=5.0)
        await scheduler.stop()

        # 15*2^1=30, 15*2^2=60, 15*2^3=120, min(15*2^4, 150)=150, apoi interval normal (600s) la succes
        assert observed_failures == [1, 2, 3, 4, 0]
        assert weather_delays == [30.0, 60.0, 120.0, 150.0, 600.0]
        assert weather.calls == 5
        assert scheduler.get_state("weather").last_error is None

        env = await cache.get_weather()
        assert env.meta.is_stale is False
        assert env.data.current.temperature_c == 12.5

        await cache.aclose()
        db.close()

    asyncio.run(_run())


def test_scheduler_respects_http_429_retry_after(tmp_path):
    """Verifică respectarea Retry-After la HTTP 429 (când depășește backoff-ul și când e mai mic)."""
    async def _run():
        db = SQLiteDatabase(tmp_path / "retry429.db")
        config = SQLiteConfigStore(db)
        weather = _ScriptedWeather([
            SourceError("weather", "HTTP 429 Too Many Requests", retry_after_s=120.0),
            SourceError("weather", "HTTP 429 Too Many Requests", retry_after_s=10.0),
        ])
        cache = SQLiteCacheManager(
            config,
            db,
            mail_provider=_DummyMail(),
            weather_provider=weather,
            news_provider=_DummyNews(),
        )
        scheduler = CacheScheduler(
            cache,
            config,
            backoff_base_s=15.0,
            backoff_max_s=900.0,
            jitter_ratio=0.0,
            run_immediately=True,
        )

        weather_delays: list[float] = []

        async def _fake_wait(source, delay_s: float) -> bool:
            if source != "weather":
                return False
            weather_delays.append(delay_s)
            await asyncio.sleep(0)
            return len(weather_delays) < 2

        scheduler._wait_interruptible = _fake_wait  # type: ignore[method-assign]

        await scheduler.start()
        await asyncio.wait_for(asyncio.gather(*scheduler._tasks.values()), timeout=5.0)
        await scheduler.stop()

        # Eroarea 1: backoff=30s < retry_after=120s -> folosește 120s
        # Eroarea 2: backoff=60s > retry_after=10s  -> păstrează backoff-ul de 60s
        assert weather_delays == [120.0, 60.0]
        assert scheduler.get_state("weather").consecutive_failures == 2
        assert "429" in (scheduler.get_state("weather").last_error or "")

        await cache.aclose()
        db.close()

    asyncio.run(_run())


def test_scheduler_waits_for_429_retry_after_in_real_loop(tmp_path):
    """Verifică în bucla reală că scheduler-ul nu reîncearcă înainte de expirarea Retry-After."""
    async def _run():
        db = SQLiteDatabase(tmp_path / "retry429_real.db")
        config = SQLiteConfigStore(db)
        weather = _FlakyWeather(fail=True, retry_after_s=0.35)
        cache = SQLiteCacheManager(
            config,
            db,
            mail_provider=_DummyMail(),
            weather_provider=weather,
            news_provider=_DummyNews(),
        )
        scheduler = CacheScheduler(
            cache,
            config,
            backoff_base_s=0.02,
            backoff_max_s=1.0,
            jitter_ratio=0.0,
            run_immediately=True,
        )

        await scheduler.start()
        await asyncio.sleep(0.12)
        # Deși backoff-ul calculat ar fi 0.04s, Retry-After (0.35s) previne retry-ul prematur
        assert weather.calls == 1

        await asyncio.sleep(0.35)
        assert weather.calls >= 2

        await scheduler.stop()
        await cache.aclose()
        db.close()

    asyncio.run(_run())


def test_scheduler_skips_disabled_widget_and_triggers_single_source(tmp_path):
    """Verifică omiterea widget-urilor dezactivate și trezirea selectivă cu trigger_refresh."""
    async def _run():
        db = SQLiteDatabase(tmp_path / "disabled.db")
        config = SQLiteConfigStore(db)
        cfg = await config.get_config()
        for w in cfg.widgets:
            if w.type == "news":
                w.enabled = False
        await config.save_config(cfg)

        mail = _DummyMail()
        weather = _FlakyWeather(fail=False)
        news = _DummyNews()
        cache = SQLiteCacheManager(
            config,
            db,
            mail_provider=mail,
            weather_provider=weather,
            news_provider=news,
        )
        scheduler = CacheScheduler(
            cache,
            config,
            run_immediately=False,
        )

        await scheduler.start()
        await asyncio.sleep(0.08)
        assert mail.calls == 0 and weather.calls == 0 and news.calls == 0

        # Trezim doar vremea și știrile (știrile fiind dezactivate nu trebuie să apeleze provider-ul)
        scheduler.trigger_refresh("weather")
        scheduler.trigger_refresh("news")
        await asyncio.sleep(0.15)

        assert weather.calls == 1
        assert news.calls == 0
        assert mail.calls == 0

        await scheduler.stop()
        await cache.aclose()
        db.close()

    asyncio.run(_run())