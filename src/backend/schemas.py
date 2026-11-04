"""Modelele de date unificate ale Smart Touch Dashboard (contract v1).

Sursa unică de adevăr pentru formatul datelor. Toate modulele (adaptoare,
cache, securitate, frontend) folosesc aceste modele. Orice modificare se face
prin PR cu review de la TL și se anunță echipei.

Convenții:
- Toate datele temporale sunt `datetime` cu fus orar (UTC) și se serializează ISO 8601.
- Unități: temperatură °C, vânt km/h, memorie MB, latență ms.
- Fiecare răspuns de date de la API este împachetat în `Envelope[T]`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, HttpUrl

SCHEMA_VERSION = "1.0.0"

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Metadate comune (folosite de CACHE și afișate de FE ca „vârsta datelor”)
# ---------------------------------------------------------------------------

class DataSource(str, Enum):
    LIVE = "live"    # proaspăt de la sursa externă
    CACHE = "cache"  # servit din cache-ul local
    MOCK = "mock"    # furnizor mock (ex. Mock-Email)


class DataMeta(BaseModel):
    source: DataSource
    fetched_at: datetime = Field(description="Momentul achiziției de la sursa externă")
    age_seconds: int = Field(ge=0, description="Vârsta datelor la momentul răspunsului")
    is_stale: bool = Field(description="True dacă TTL-ul a expirat (afișează „Mod Offline”)")
    error: str | None = Field(default=None, description="Ultima eroare a sursei, dacă există")


class Envelope(BaseModel, Generic[T]):
    """Împachetarea standard pentru orice răspuns de date."""
    data: T
    meta: DataMeta


# ---------------------------------------------------------------------------
# Email (MAIL-1, MAIL-2)
# ---------------------------------------------------------------------------

class EmailSummary(BaseModel):
    """Element din listă. Nu conține corpul mesajului (vizibil fără PIN)."""
    id: str
    sender_name: str
    sender_address: str
    subject: str
    received_at: datetime
    is_read: bool = False
    is_priority: bool = False


class EmailDetail(EmailSummary):
    """Previzualizare completă. Accesibilă doar cu sesiune deblocată (SEC)."""
    preview: str = Field(max_length=500, description="Text sanitizat, fără HTML, trunchiat")


class EmailFilter(str, Enum):
    ALL = "all"
    UNREAD = "unread"
    PRIORITY = "priority"


class EmailList(BaseModel):
    items: list[EmailSummary]
    unread_count: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Vreme (DATA-WN)
# ---------------------------------------------------------------------------

class WeatherCondition(str, Enum):
    CLEAR = "clear"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    FOG = "fog"
    DRIZZLE = "drizzle"
    RAIN = "rain"
    SNOW = "snow"
    THUNDERSTORM = "thunderstorm"
    UNKNOWN = "unknown"


class WeatherCurrent(BaseModel):
    temperature_c: float
    feels_like_c: float
    humidity_pct: int = Field(ge=0, le=100)
    wind_kmh: float = Field(ge=0)
    condition: WeatherCondition
    description: str


class WeatherForecastPoint(BaseModel):
    time: datetime
    temperature_c: float
    temperature_min_c: float | None = None  # doar pentru prognoza zilnică
    temperature_max_c: float | None = None
    precipitation_pct: int | None = Field(default=None, ge=0, le=100)
    condition: WeatherCondition


class WeatherData(BaseModel):
    location_name: str
    latitude: float
    longitude: float
    current: WeatherCurrent
    hourly: list[WeatherForecastPoint] = []
    daily: list[WeatherForecastPoint] = []


# ---------------------------------------------------------------------------
# Știri / RSS (DATA-WN)
# ---------------------------------------------------------------------------

class NewsSource(BaseModel):
    id: str
    name: str
    url: HttpUrl
    enabled: bool = True


class NewsSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: HttpUrl


class NewsSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    enabled: bool | None = None


class NewsItem(BaseModel):
    id: str = Field(description="Hash stabil (ex. sha1 al link-ului) pentru deduplicare")
    source_id: str
    source_name: str
    title: str
    summary: str = Field(default="", max_length=600, description="Text curățat de HTML")
    link: HttpUrl
    published_at: datetime


class NewsList(BaseModel):
    items: list[NewsItem]  # ordonate descrescător după published_at


# ---------------------------------------------------------------------------
# Configurare widget-uri (FE-2, persistată de CACHE)
# ---------------------------------------------------------------------------

WidgetType = Literal["email", "weather", "news", "system"]


class WidgetConfig(BaseModel):
    type: WidgetType
    enabled: bool = True
    position: int = Field(ge=0, description="Ordinea pe ecran (0 = primul)")
    refresh_interval_s: int = Field(ge=30, le=3600, description="Interval de reîmprospătare")


class DashboardConfig(BaseModel):
    widgets: list[WidgetConfig]
    location_name: str = "Brașov"
    latitude: float = 45.6427
    longitude: float = 25.5887
    auto_lock_minutes: int = Field(default=5, ge=1, le=60)
    theme: Literal["light", "dark", "auto"] = "auto"


# ---------------------------------------------------------------------------
# Telemetrie și monitorizare (DEVOPS + CACHE)
# ---------------------------------------------------------------------------

class SystemMetrics(BaseModel):
    """Produs de src/monitoring/rpi_metrics.py (DEVOPS)."""
    timestamp: datetime
    cpu_temp_c: float | None = Field(description="None dacă senzorul nu e disponibil (ex. pe laptop)")
    cpu_load_pct: float = Field(ge=0, le=100)
    ram_used_mb: float = Field(ge=0)
    ram_total_mb: float = Field(ge=0)
    online: bool


class SourceTelemetry(BaseModel):
    """Produs de src/cache/ (CACHE)."""
    source: Literal["email", "weather", "news"]
    last_latency_ms: float | None = None
    avg_latency_ms: float | None = None
    cache_hits: int = 0
    cache_misses: int = 0
    last_success_at: datetime | None = None
    consecutive_failures: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total else 0.0


class TelemetrySnapshot(BaseModel):
    system: SystemMetrics
    sources: list[SourceTelemetry]


# ---------------------------------------------------------------------------
# Autentificare (SEC)
# ---------------------------------------------------------------------------

class UnlockRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class SessionInfo(BaseModel):
    token: str
    expires_at: datetime


class AuthStatus(BaseModel):
    unlocked: bool
    expires_at: datetime | None = None
    failed_attempts: int = 0
    locked_out_until: datetime | None = None


# ---------------------------------------------------------------------------
# Evenimente WebSocket (backend -> frontend)
# ---------------------------------------------------------------------------

class WsEventType(str, Enum):
    DATA_UPDATED = "data_updated"          # payload: {"widget": "email|weather|news"}
    CONNECTIVITY = "connectivity_changed"  # payload: {"online": bool}
    AUTH_LOCKED = "auth_locked"            # payload: {}
    METRICS = "metrics"                    # payload: SystemMetrics
    CONFIG_UPDATED = "config_updated"      # payload: {}


class WsEvent(BaseModel):
    type: WsEventType
    timestamp: datetime
    payload: dict = {}


# ---------------------------------------------------------------------------
# Erori și health
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    code: str = Field(description="Cod stabil, ex. AUTH_REQUIRED, SOURCE_UNAVAILABLE")
    message: str


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    schema_version: str = SCHEMA_VERSION
    online: bool
    mail_mode: Literal["real", "mock"]
