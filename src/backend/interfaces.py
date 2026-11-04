"""Interfețele (contractele) dintre modulele echipei.

Fiecare modul implementează Protocol-ul său; app.py depinde DOAR de aceste
interfețe, nu de implementări. Până la livrarea modulelor reale, app.py
folosește implementările din mock_services.py.

Flux:  Adaptoare (MAIL / DATA-WN) -> CacheService + Scheduler (CACHE) -> app.py -> FE
"""

from __future__ import annotations

from typing import Protocol

from .schemas import (
    AuthStatus,
    DashboardConfig,
    EmailDetail,
    EmailFilter,
    EmailList,
    Envelope,
    NewsItem,
    NewsList,
    NewsSource,
    NewsSourceCreate,
    NewsSourceUpdate,
    SessionInfo,
    SourceTelemetry,
    SystemMetrics,
    WeatherData,
)


class SourceError(Exception):
    """Ridicată de adaptoare când sursa externă eșuează (rețea, HTTP 4xx/5xx, timeout, parsare).

    CACHE o prinde, aplică backoff și servește datele vechi din cache.
    """

    def __init__(self, source: str, message: str, retry_after_s: float | None = None):
        super().__init__(f"[{source}] {message}")
        self.source = source
        self.retry_after_s = retry_after_s  # ex. din header-ul Retry-After la HTTP 429


class AuthError(Exception):
    """Ridicată de AuthService la PIN greșit sau blocare temporară."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # INVALID_PIN | LOCKED_OUT


# ---------------------------------------------------------------------------
# Adaptoare de achiziție: apelează sursa externă și returnează date normalizate.
# Nu știu nimic de cache sau HTTP-ul intern. La eșec ridică SourceError.
# ---------------------------------------------------------------------------

class MailProvider(Protocol):
    """MAIL-1 (real: IMAP/OAuth2) și MAIL-2 (mock). Comutare prin MAIL_MODE."""

    mode: str  # "real" | "mock"

    async def fetch_inbox(self, limit: int = 50) -> list[EmailDetail]: ...


class WeatherProvider(Protocol):
    """DATA-WN: src/adapters/weather_adapter.py"""

    async def fetch(self, latitude: float, longitude: float, location_name: str) -> WeatherData: ...


class NewsProvider(Protocol):
    """DATA-WN: src/adapters/news_rss_adapter.py. Deduplicat, ordonat descrescător."""

    async def fetch(self, sources: list[NewsSource]) -> list[NewsItem]: ...


# ---------------------------------------------------------------------------
# Cache și persistență (CACHE): singura sursă de date pentru app.py.
# Nu ridică excepții pentru surse căzute: întoarce date vechi cu meta.is_stale=True.
# ---------------------------------------------------------------------------

class CacheService(Protocol):
    async def get_emails(self, filter: EmailFilter, limit: int) -> Envelope[EmailList]: ...

    async def get_email(self, email_id: str) -> Envelope[EmailDetail] | None: ...

    async def mark_read(self, email_id: str) -> None: ...

    async def get_weather(self) -> Envelope[WeatherData]: ...

    async def get_news(self, source_id: str | None, limit: int) -> Envelope[NewsList]: ...

    async def refresh(self, widget: str) -> None:
        """Forțează reîmprospătarea unei surse (cu respectarea rate limiting)."""
        ...

    async def get_telemetry(self) -> list[SourceTelemetry]: ...


class ConfigStore(Protocol):
    """CACHE: persistența configurației widget-urilor și a surselor RSS."""

    async def get_config(self) -> DashboardConfig: ...

    async def save_config(self, config: DashboardConfig) -> DashboardConfig: ...

    async def list_news_sources(self) -> list[NewsSource]: ...

    async def add_news_source(self, data: NewsSourceCreate) -> NewsSource: ...

    async def update_news_source(self, source_id: str, data: NewsSourceUpdate) -> NewsSource | None: ...

    async def delete_news_source(self, source_id: str) -> bool: ...


# ---------------------------------------------------------------------------
# Securitate (SEC): src/security/auth_manager.py
# ---------------------------------------------------------------------------

class AuthService(Protocol):
    def unlock(self, pin: str) -> SessionInfo:
        """Ridică AuthError dacă PIN-ul e greșit sau sesiunea e blocată temporar."""
        ...

    def lock(self, token: str | None) -> None: ...

    def validate(self, token: str | None) -> bool:
        """True dacă token-ul e valid; prelungește sesiunea (activitate)."""
        ...

    def status(self, token: str | None) -> AuthStatus: ...


# ---------------------------------------------------------------------------
# Monitorizare (DEVOPS): src/monitoring/rpi_metrics.py
# ---------------------------------------------------------------------------

class MetricsProvider(Protocol):
    def read(self) -> SystemMetrics: ...
