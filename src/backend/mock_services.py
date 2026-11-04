"""Implementări mock ale interfețelor din interfaces.py.

Scop: frontend-ul și testele pot lucra din ziua 1, fără adaptoare reale.
Fiecare clasă se înlocuiește cu implementarea modulului responsabil:
  MockCacheService / MockConfigStore -> CACHE
  MockAuthService                    -> SEC
  MockMetricsProvider                -> DEVOPS
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from .interfaces import AuthError
from .schemas import (
    AuthStatus,
    DashboardConfig,
    DataMeta,
    DataSource,
    EmailDetail,
    EmailFilter,
    EmailList,
    EmailSummary,
    Envelope,
    NewsItem,
    NewsList,
    NewsSource,
    NewsSourceCreate,
    NewsSourceUpdate,
    SessionInfo,
    SourceTelemetry,
    SystemMetrics,
    WeatherCondition,
    WeatherCurrent,
    WeatherData,
    WeatherForecastPoint,
    WidgetConfig,
)

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _meta(source: DataSource = DataSource.MOCK) -> DataMeta:
    return DataMeta(source=source, fetched_at=_now(), age_seconds=0, is_stale=False)


# ---------------------------------------------------------------------------
# Date demonstrative
# ---------------------------------------------------------------------------

def _demo_emails() -> list[EmailDetail]:
    now = _now()
    rows = [
        ("Secretariat FIESC", "secretariat@unitbv.ro", "Programarea examenelor - sesiunea de iarnă",
         "Vă transmitem programarea provizorie a examenelor pentru sesiunea de iarnă.", False, True, 15),
        ("Dragoș Bratu", "dragos.bratu@unitbv.ro", "APD - prezentare intermediară proiect",
         "Vă rog să pregătiți o scurtă demonstrație a stadiului proiectului la laborator.", False, True, 90),
        ("Biblioteca UNITBV", "biblioteca@unitbv.ro", "Acces baze de date IEEE Xplore",
         "Accesul la IEEE Xplore este disponibil din rețeaua universității.", True, False, 300),
        ("e-Learning", "noreply@elearning.unitbv.ro", "Material nou: Curs 6 APD",
         "A fost încărcat un material nou la disciplina APD.", True, False, 1440),
    ]
    return [
        EmailDetail(
            id=f"mock-{i}", sender_name=n, sender_address=a, subject=s, preview=p,
            received_at=now - timedelta(minutes=m), is_read=r, is_priority=pr,
        )
        for i, (n, a, s, p, r, pr, m) in enumerate(rows, start=1)
    ]


def _demo_weather() -> WeatherData:
    now = _now().replace(minute=0, second=0, microsecond=0)
    return WeatherData(
        location_name="Brașov", latitude=45.6427, longitude=25.5887,
        current=WeatherCurrent(temperature_c=6.5, feels_like_c=3.8, humidity_pct=71, wind_kmh=12.0,
                               condition=WeatherCondition.PARTLY_CLOUDY, description="Parțial noros"),
        hourly=[WeatherForecastPoint(time=now + timedelta(hours=h), temperature_c=6.5 - h * 0.4,
                                     precipitation_pct=10 * h, condition=WeatherCondition.CLOUDY)
                for h in range(1, 7)],
        daily=[WeatherForecastPoint(time=now + timedelta(days=d), temperature_c=7, temperature_min_c=1,
                                    temperature_max_c=9 + d, precipitation_pct=20,
                                    condition=WeatherCondition.RAIN if d == 2 else WeatherCondition.CLEAR)
               for d in range(1, 4)],
    )


# ---------------------------------------------------------------------------
# CACHE (mock)
# ---------------------------------------------------------------------------

class MockConfigStore:
    def __init__(self) -> None:
        self._config = DashboardConfig(widgets=[
            WidgetConfig(type="weather", position=0, refresh_interval_s=600),
            WidgetConfig(type="email", position=1, refresh_interval_s=120),
            WidgetConfig(type="news", position=2, refresh_interval_s=900),
            WidgetConfig(type="system", position=3, refresh_interval_s=30),
        ])
        self._sources: dict[str, NewsSource] = {}
        for name, url in [("UNITBV", "https://www.unitbv.ro/rss"),
                          ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index")]:
            src = NewsSource(id=hashlib.sha1(url.encode()).hexdigest()[:10], name=name, url=url)
            self._sources[src.id] = src

    async def get_config(self) -> DashboardConfig:
        return self._config

    async def save_config(self, config: DashboardConfig) -> DashboardConfig:
        self._config = config
        return config

    async def list_news_sources(self) -> list[NewsSource]:
        return list(self._sources.values())

    async def add_news_source(self, data: NewsSourceCreate) -> NewsSource:
        src = NewsSource(id=hashlib.sha1(str(data.url).encode()).hexdigest()[:10], name=data.name, url=data.url)
        self._sources[src.id] = src
        return src

    async def update_news_source(self, source_id: str, data: NewsSourceUpdate) -> NewsSource | None:
        src = self._sources.get(source_id)
        if src is None:
            return None
        updated = src.model_copy(update=data.model_dump(exclude_none=True))
        self._sources[source_id] = updated
        return updated

    async def delete_news_source(self, source_id: str) -> bool:
        return self._sources.pop(source_id, None) is not None


class MockCacheService:
    def __init__(self, config_store: MockConfigStore) -> None:
        self._emails = {e.id: e for e in _demo_emails()}
        self._config_store = config_store

    async def get_emails(self, filter: EmailFilter, limit: int) -> Envelope[EmailList]:
        items = sorted(self._emails.values(), key=lambda e: e.received_at, reverse=True)
        if filter is EmailFilter.UNREAD:
            items = [e for e in items if not e.is_read]
        elif filter is EmailFilter.PRIORITY:
            items = [e for e in items if e.is_priority]
        summaries = [EmailSummary(**e.model_dump(exclude={"preview"})) for e in items[:limit]]
        unread = sum(1 for e in self._emails.values() if not e.is_read)
        return Envelope[EmailList](data=EmailList(items=summaries, unread_count=unread), meta=_meta())

    async def get_email(self, email_id: str) -> Envelope[EmailDetail] | None:
        email = self._emails.get(email_id)
        return Envelope[EmailDetail](data=email, meta=_meta()) if email else None

    async def mark_read(self, email_id: str) -> None:
        if email_id in self._emails:
            self._emails[email_id] = self._emails[email_id].model_copy(update={"is_read": True})

    async def get_weather(self) -> Envelope[WeatherData]:
        return Envelope[WeatherData](data=_demo_weather(), meta=_meta())

    async def get_news(self, source_id: str | None, limit: int) -> Envelope[NewsList]:
        now = _now()
        sources = [s for s in await self._config_store.list_news_sources() if s.enabled]
        if source_id:
            sources = [s for s in sources if s.id == source_id]
        items = [
            NewsItem(id=f"{s.id}-{i}", source_id=s.id, source_name=s.name,
                     title=f"[{s.name}] Știre demonstrativă #{i}",
                     summary="Rezumat scurt al știrii, curățat de HTML.",
                     link=f"https://example.com/{s.id}/{i}", published_at=now - timedelta(hours=i))
            for s in sources for i in range(1, 4)
        ]
        items.sort(key=lambda n: n.published_at, reverse=True)
        return Envelope[NewsList](data=NewsList(items=items[:limit]), meta=_meta())

    async def refresh(self, widget: str) -> None:
        return None

    async def get_telemetry(self) -> list[SourceTelemetry]:
        return [SourceTelemetry(source=s, last_latency_ms=1.0, avg_latency_ms=1.0, cache_hits=0,
                                cache_misses=0, last_success_at=_now())
                for s in ("email", "weather", "news")]


# ---------------------------------------------------------------------------
# SEC (mock): PIN din variabila de mediu DASHBOARD_PIN; niciodată în Git.
# ---------------------------------------------------------------------------

class MockAuthService:
    MAX_ATTEMPTS = 5
    LOCKOUT = timedelta(seconds=60)

    def __init__(self, session_minutes: int = 5) -> None:
        pin = os.environ.get("DASHBOARD_PIN")
        if not pin:
            pin = "1234"
            log.warning("DASHBOARD_PIN nu este setat; se folosește PIN-ul de dezvoltare 1234 (doar mock).")
        self._pin = pin
        self._session = timedelta(minutes=session_minutes)
        self._sessions: dict[str, datetime] = {}
        self._failed = 0
        self._locked_until: datetime | None = None

    def unlock(self, pin: str) -> SessionInfo:
        now = _now()
        if self._locked_until and now < self._locked_until:
            raise AuthError("LOCKED_OUT", "Prea multe încercări. Reîncearcă mai târziu.")
        if not secrets.compare_digest(pin, self._pin):
            self._failed += 1
            if self._failed >= self.MAX_ATTEMPTS:
                self._locked_until = now + self.LOCKOUT
                self._failed = 0
            raise AuthError("INVALID_PIN", "PIN incorect.")
        self._failed = 0
        token = secrets.token_urlsafe(32)
        self._sessions[token] = now + self._session
        return SessionInfo(token=token, expires_at=self._sessions[token])

    def lock(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def validate(self, token: str | None) -> bool:
        if not token or token not in self._sessions:
            return False
        if _now() >= self._sessions[token]:
            del self._sessions[token]
            return False
        self._sessions[token] = _now() + self._session  # prelungire la activitate
        return True

    def status(self, token: str | None) -> AuthStatus:
        valid = self.validate(token)
        return AuthStatus(unlocked=valid, expires_at=self._sessions.get(token) if valid else None,
                          failed_attempts=self._failed, locked_out_until=self._locked_until)


# ---------------------------------------------------------------------------
# DEVOPS (mock)
# ---------------------------------------------------------------------------

class MockMetricsProvider:
    def read(self) -> SystemMetrics:
        return SystemMetrics(timestamp=_now(), cpu_temp_c=48.5, cpu_load_pct=12.0,
                             ram_used_mb=820.0, ram_total_mb=3792.0, online=True)
