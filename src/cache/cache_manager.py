"""Cache SQLite, stocare configurație și telemetrie pentru Smart Touch Dashboard.

Implementează protocoalele `ConfigStore` și `CacheService` din
`src/backend/interfaces.py`:
  - `SQLiteConfigStore`: persistă configurarea widget-urilor, setările generale
    ale dashboard-ului și sursele RSS în SQLite.
  - `SQLiteCacheManager`: citește/scrie datele surselor (email, weather, news)
    cu TTL configurabil per widget, stale-while-revalidate, fallback offline
    fără excepții (meta.is_stale=True) și telemetrie hit/miss + latență.

Notă de ne-blocare: toate operațiile SQLite rulează prin `asyncio.to_thread`
protejate de un lock per conexiune (WAL mode), astfel încât bucla de evenimente
FastAPI să nu fie blocată.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from src.backend.interfaces import (
    ConfigStore,
    MailProvider,
    NewsProvider,
    SourceError,
    WeatherProvider,
)
from src.backend.schemas import (
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
    SourceTelemetry,
    WeatherCondition,
    WeatherCurrent,
    WeatherData,
    WidgetConfig,
)

log = logging.getLogger("dashboard.cache")

SourceName = Literal["email", "weather", "news"]
CACHE_SOURCES: tuple[SourceName, ...] = ("email", "weather", "news")

DEFAULT_DB_PATH = Path("data/dashboard_cache.db")

# Intervale implicite conform docs/widget_specifications.md și mock_services.py
DEFAULT_TTLS: dict[str, int] = {
    "email": 120,
    "weather": 600,
    "news": 900,
    "system": 30,
}

DEFAULT_WIDGETS: tuple[WidgetConfig, ...] = (
    WidgetConfig(type="weather", enabled=True, position=0, refresh_interval_s=600),
    WidgetConfig(type="email", enabled=True, position=1, refresh_interval_s=120),
    WidgetConfig(type="news", enabled=True, position=2, refresh_interval_s=900),
    WidgetConfig(type="system", enabled=True, position=3, refresh_interval_s=30),
)

DEFAULT_NEWS_SOURCES: tuple[tuple[str, str], ...] = (
    ("UNITBV", "https://www.unitbv.ro/rss"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
)

# Limită maximă de rânduri în tabelul telemetry pentru a preveni creșterea necontrolată (rulare 60+ min)
MAX_TELEMETRY_ROWS = 10_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _source_id_for_url(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


@dataclass(slots=True)
class RefreshResult:
    """Rezultatul unei încercări de actualizare a unei surse (folosit și de scheduler)."""

    widget: str
    success: bool
    latency_ms: float
    error: str | None = None
    retry_after_s: float | None = None
    skipped: bool = False


class SQLiteDatabase:
    """Wrapper thread-safe peste sqlite3 cu schema completă a modulului CACHE."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            if self.db_path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    source        TEXT NOT NULL,
                    cache_key     TEXT NOT NULL,
                    payload_json  TEXT NOT NULL,
                    origin_source TEXT NOT NULL DEFAULT 'live',
                    fetched_at    TEXT NOT NULL,
                    expires_at    TEXT NOT NULL,
                    last_error    TEXT,
                    PRIMARY KEY (source, cache_key)
                );

                CREATE TABLE IF NOT EXISTS widget_config (
                    type               TEXT PRIMARY KEY,
                    enabled            INTEGER NOT NULL DEFAULT 1,
                    position           INTEGER NOT NULL,
                    refresh_interval_s INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dashboard_settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS news_sources (
                    id      TEXT PRIMARY KEY,
                    name    TEXT NOT NULL,
                    url     TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS telemetry (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source      TEXT NOT NULL,
                    operation   TEXT NOT NULL,
                    latency_ms  REAL NOT NULL,
                    cache_hit   INTEGER NOT NULL,
                    status      TEXT NOT NULL,
                    error       TEXT,
                    recorded_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_source_time
                    ON telemetry (source, recorded_at);

                CREATE TABLE IF NOT EXISTS source_state (
                    source               TEXT PRIMARY KEY,
                    last_success_at      TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_error           TEXT
                );

                CREATE TABLE IF NOT EXISTS email_read_state (
                    email_id  TEXT PRIMARY KEY,
                    marked_at TEXT NOT NULL
                );
                """
            )
            for source in CACHE_SOURCES:
                self._conn.execute(
                    "INSERT OR IGNORE INTO source_state (source, consecutive_failures) VALUES (?, 0)",
                    (source,),
                )
            self._conn.commit()

    def execute_sync(self, fn):
        """Rulează o funcție sincronă sub lock-ul bazei de date."""
        with self._lock:
            return fn(self._conn)

    async def run(self, fn):
        """Rulează operația SQLite într-un thread separat (fără a bloca event loop-ul)."""
        return await asyncio.to_thread(self.execute_sync, fn)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# ConfigStore (SQLite)
# ---------------------------------------------------------------------------

class SQLiteConfigStore:
    """Persistența în SQLite a configurației widget-urilor și a surselor RSS."""

    def __init__(
        self,
        db: SQLiteDatabase | str | Path = DEFAULT_DB_PATH,
        *,
        seed_defaults: bool = True,
    ) -> None:
        self._owns_db = not isinstance(db, SQLiteDatabase)
        self._db = db if isinstance(db, SQLiteDatabase) else SQLiteDatabase(db)
        if seed_defaults:
            self._seed_defaults_sync()

    @property
    def db(self) -> SQLiteDatabase:
        return self._db

    def _seed_defaults_sync(self) -> None:
        def _op(conn: sqlite3.Connection) -> None:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM widget_config").fetchone()
            if row["cnt"] == 0:
                conn.executemany(
                    """
                    INSERT INTO widget_config (type, enabled, position, refresh_interval_s)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (w.type, int(w.enabled), w.position, w.refresh_interval_s)
                        for w in DEFAULT_WIDGETS
                    ],
                )

            env_lat = os.environ.get("WEATHER_LAT", "45.6427")
            env_lon = os.environ.get("WEATHER_LON", "25.5887")
            env_lock = os.environ.get("SESSION_TIMEOUT_MIN", "5")
            try:
                lock_min = max(1, min(60, int(env_lock)))
            except ValueError:
                lock_min = 5

            default_settings = {
                "location_name": "Brașov",
                "latitude": str(float(env_lat)),
                "longitude": str(float(env_lon)),
                "auto_lock_minutes": str(lock_min),
                "theme": "auto",
            }
            for key, value in default_settings.items():
                conn.execute(
                    "INSERT OR IGNORE INTO dashboard_settings (key, value) VALUES (?, ?)",
                    (key, value),
                )

            seeded = conn.execute(
                "SELECT value FROM dashboard_settings WHERE key = 'news_sources_seeded'"
            ).fetchone()
            if seeded is None:
                for name, url in DEFAULT_NEWS_SOURCES:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO news_sources (id, name, url, enabled)
                        VALUES (?, ?, ?, 1)
                        """,
                        (_source_id_for_url(url), name, url),
                    )
                conn.execute(
                    "INSERT INTO dashboard_settings (key, value) VALUES ('news_sources_seeded', '1')"
                )
            conn.commit()

        self._db.execute_sync(_op)

    async def get_config(self) -> DashboardConfig:
        def _op(conn: sqlite3.Connection) -> DashboardConfig:
            widget_rows = conn.execute(
                "SELECT type, enabled, position, refresh_interval_s FROM widget_config ORDER BY position ASC"
            ).fetchall()
            widgets = [
                WidgetConfig(
                    type=r["type"],
                    enabled=bool(r["enabled"]),
                    position=r["position"],
                    refresh_interval_s=r["refresh_interval_s"],
                )
                for r in widget_rows
            ]
            if not widgets:
                widgets = list(DEFAULT_WIDGETS)

            settings_rows = conn.execute("SELECT key, value FROM dashboard_settings").fetchall()
            settings = {r["key"]: r["value"] for r in settings_rows}
            return DashboardConfig(
                widgets=widgets,
                location_name=settings.get("location_name", "Brașov"),
                latitude=float(settings.get("latitude", "45.6427")),
                longitude=float(settings.get("longitude", "25.5887")),
                auto_lock_minutes=int(settings.get("auto_lock_minutes", "5")),
                theme=settings.get("theme", "auto"),
            )

        return await self._db.run(_op)

    async def save_config(self, config: DashboardConfig) -> DashboardConfig:
        def _op(conn: sqlite3.Connection) -> DashboardConfig:
            conn.execute("DELETE FROM widget_config")
            conn.executemany(
                """
                INSERT INTO widget_config (type, enabled, position, refresh_interval_s)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (w.type, int(w.enabled), w.position, w.refresh_interval_s)
                    for w in config.widgets
                ],
            )
            settings = {
                "location_name": config.location_name,
                "latitude": str(config.latitude),
                "longitude": str(config.longitude),
                "auto_lock_minutes": str(config.auto_lock_minutes),
                "theme": config.theme,
            }
            conn.executemany(
                "INSERT OR REPLACE INTO dashboard_settings (key, value) VALUES (?, ?)",
                list(settings.items()),
            )
            conn.commit()
            return config

        return await self._db.run(_op)

    async def list_news_sources(self) -> list[NewsSource]:
        def _op(conn: sqlite3.Connection) -> list[NewsSource]:
            rows = conn.execute(
                "SELECT id, name, url, enabled FROM news_sources ORDER BY name ASC"
            ).fetchall()
            return [
                NewsSource(
                    id=r["id"],
                    name=r["name"],
                    url=r["url"],
                    enabled=bool(r["enabled"]),
                )
                for r in rows
            ]

        return await self._db.run(_op)

    async def add_news_source(self, data: NewsSourceCreate) -> NewsSource:
        url_str = str(data.url)
        src = NewsSource(
            id=_source_id_for_url(url_str),
            name=data.name,
            url=data.url,
            enabled=True,
        )

        def _op(conn: sqlite3.Connection) -> NewsSource:
            conn.execute(
                """
                INSERT OR REPLACE INTO news_sources (id, name, url, enabled)
                VALUES (?, ?, ?, ?)
                """,
                (src.id, src.name, url_str, int(src.enabled)),
            )
            conn.commit()
            return src

        return await self._db.run(_op)

    async def update_news_source(
        self, source_id: str, data: NewsSourceUpdate
    ) -> NewsSource | None:
        def _op(conn: sqlite3.Connection) -> NewsSource | None:
            row = conn.execute(
                "SELECT id, name, url, enabled FROM news_sources WHERE id = ?",
                (source_id,),
            ).fetchone()
            if row is None:
                return None
            existing = NewsSource(
                id=row["id"],
                name=row["name"],
                url=row["url"],
                enabled=bool(row["enabled"]),
            )
            updated = existing.model_copy(update=data.model_dump(exclude_none=True))
            conn.execute(
                "UPDATE news_sources SET name = ?, enabled = ? WHERE id = ?",
                (updated.name, int(updated.enabled), source_id),
            )
            conn.commit()
            return updated

        return await self._db.run(_op)

    async def delete_news_source(self, source_id: str) -> bool:
        def _op(conn: sqlite3.Connection) -> bool:
            cur = conn.execute("DELETE FROM news_sources WHERE id = ?", (source_id,))
            conn.commit()
            return cur.rowcount > 0

        return await self._db.run(_op)

    def close(self) -> None:
        if self._owns_db:
            self._db.close()


# ---------------------------------------------------------------------------
# CacheService (SQLite + SWR + Fallback Offline + Telemetrie)
# ---------------------------------------------------------------------------

class SQLiteCacheManager:
    """Implementarea reală a `CacheService` cu persistență SQLite și mod offline."""

    def __init__(
        self,
        config_store: ConfigStore,
        db: SQLiteDatabase | str | Path = DEFAULT_DB_PATH,
        *,
        mail_provider: MailProvider | None = None,
        weather_provider: WeatherProvider | None = None,
        news_provider: NewsProvider | None = None,
        ttls: dict[str, int] | None = None,
        min_manual_refresh_interval_s: float = 5.0,
        email_fetch_limit: int = 50,
    ) -> None:
        self._config_store = config_store
        if isinstance(db, SQLiteDatabase):
            self._db = db
            self._owns_db = False
        elif isinstance(config_store, SQLiteConfigStore) and str(db) == config_store.db.db_path:
            self._db = config_store.db
            self._owns_db = False
        else:
            self._db = SQLiteDatabase(db)
            self._owns_db = True

        self._mail_provider = mail_provider
        self._weather_provider = weather_provider
        self._news_provider = news_provider
        self._ttl_overrides = dict(ttls or {})
        self._min_manual_refresh_interval_s = min_manual_refresh_interval_s
        self._email_fetch_limit = email_fetch_limit

        self._refresh_locks: dict[str, asyncio.Lock] = {
            s: asyncio.Lock() for s in CACHE_SOURCES
        }
        self._last_refresh_attempt: dict[str, float] = {}
        self._bg_tasks: set[asyncio.Task] = set()

    @property
    def db(self) -> SQLiteDatabase:
        return self._db

    def set_providers(
        self,
        *,
        mail_provider: MailProvider | None = None,
        weather_provider: WeatherProvider | None = None,
        news_provider: NewsProvider | None = None,
    ) -> None:
        """Permite conectarea ulterioară a adaptoarelor reale (MAIL / DATA-WN)."""
        if mail_provider is not None:
            self._mail_provider = mail_provider
        if weather_provider is not None:
            self._weather_provider = weather_provider
        if news_provider is not None:
            self._news_provider = news_provider

    async def get_ttl(self, source: str) -> int:
        """Returnează TTL-ul (secunde) configurat pentru o sursă."""
        if source in self._ttl_overrides:
            return self._ttl_overrides[source]
        try:
            cfg = await self._config_store.get_config()
            for widget in cfg.widgets:
                if widget.type == source:
                    return widget.refresh_interval_s
        except Exception:
            log.exception("Nu s-a putut citi TTL-ul din ConfigStore pentru %s", source)
        return DEFAULT_TTLS.get(source, 300)

    # ------------------------------------------------------------------
    # Operații interne SQLite (cache_entries, source_state, telemetry)
    # ------------------------------------------------------------------

    async def _read_entry(self, source: SourceName, cache_key: str = "default") -> dict | None:
        def _op(conn: sqlite3.Connection) -> dict | None:
            row = conn.execute(
                """
                SELECT source, cache_key, payload_json, origin_source,
                       fetched_at, expires_at, last_error
                FROM cache_entries
                WHERE source = ? AND cache_key = ?
                """,
                (source, cache_key),
            ).fetchone()
            return dict(row) if row else None

        return await self._db.run(_op)

    async def _write_entry(
        self,
        source: SourceName,
        payload_json: str,
        *,
        ttl_s: int,
        origin_source: DataSource,
        cache_key: str = "default",
        fetched_at: datetime | None = None,
    ) -> None:
        now = fetched_at or _now()
        expires_at = now + timedelta(seconds=max(1, ttl_s))

        def _op(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache_entries
                    (source, cache_key, payload_json, origin_source, fetched_at, expires_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    source,
                    cache_key,
                    payload_json,
                    origin_source.value,
                    _to_iso(now),
                    _to_iso(expires_at),
                ),
            )
            conn.execute(
                """
                INSERT INTO source_state (source, last_success_at, consecutive_failures, last_error)
                VALUES (?, ?, 0, NULL)
                ON CONFLICT(source) DO UPDATE SET
                    last_success_at = excluded.last_success_at,
                    consecutive_failures = 0,
                    last_error = NULL
                """,
                (source, _to_iso(now)),
            )
            conn.commit()

        await self._db.run(_op)

    async def _record_source_failure(self, source: SourceName, error_msg: str) -> None:
        def _op(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO source_state (source, consecutive_failures, last_error)
                VALUES (?, 1, ?)
                ON CONFLICT(source) DO UPDATE SET
                    consecutive_failures = source_state.consecutive_failures + 1,
                    last_error = excluded.last_error
                """,
                (source, error_msg),
            )
            conn.execute(
                """
                UPDATE cache_entries
                SET last_error = ?
                WHERE source = ? AND cache_key = 'default'
                """,
                (error_msg, source),
            )
            conn.commit()

        await self._db.run(_op)

    async def _get_source_last_error(self, source: SourceName) -> str | None:
        def _op(conn: sqlite3.Connection) -> str | None:
            row = conn.execute(
                "SELECT last_error FROM source_state WHERE source = ?",
                (source,),
            ).fetchone()
            return row["last_error"] if row else None

        return await self._db.run(_op)

    async def _record_telemetry(
        self,
        source: SourceName,
        *,
        operation: Literal["cache_read", "source_fetch"],
        latency_ms: float,
        cache_hit: bool,
        status: str,
        error: str | None = None,
    ) -> None:
        now_iso = _to_iso(_now())

        def _op(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO telemetry (source, operation, latency_ms, cache_hit, status, error, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (source, operation, round(latency_ms, 3), int(cache_hit), status, error, now_iso),
            )
            conn.execute(
                """
                DELETE FROM telemetry
                WHERE id NOT IN (
                    SELECT id FROM telemetry ORDER BY id DESC LIMIT ?
                )
                """,
                (MAX_TELEMETRY_ROWS,),
            )
            conn.commit()

        await self._db.run(_op)

    def _build_meta(self, entry: dict | None, fallback_error: str | None = None) -> tuple[DataMeta, bool]:
        """Construiește `DataMeta` din intrarea de cache și întoarce `(meta, needs_revalidate)`."""
        now = _now()
        if entry is None:
            meta = DataMeta(
                source=DataSource.CACHE,
                fetched_at=now,
                age_seconds=0,
                is_stale=True,
                error=fallback_error or "Date indisponibile în cache",
            )
            return meta, True

        fetched_at = _from_iso(entry["fetched_at"]) or now
        expires_at = _from_iso(entry["expires_at"]) or fetched_at
        age_seconds = max(0, int((now - fetched_at).total_seconds()))
        last_error: str | None = entry.get("last_error")
        expired = now >= expires_at
        is_stale = expired or (last_error is not None)

        if is_stale:
            data_source = DataSource.CACHE
        else:
            try:
                data_source = DataSource(entry["origin_source"])
            except ValueError:
                data_source = DataSource.LIVE

        meta = DataMeta(
            source=data_source,
            fetched_at=fetched_at,
            age_seconds=age_seconds,
            is_stale=is_stale,
            error=last_error,
        )
        return meta, is_stale

    def _has_provider(self, source: SourceName) -> bool:
        if source == "email":
            return self._mail_provider is not None
        if source == "weather":
            return self._weather_provider is not None
        if source == "news":
            return self._news_provider is not None
        return False

    def _schedule_background_refresh(self, source: SourceName) -> None:
        """Stale-while-revalidate: declanșează refresh în fundal fără a bloca cererea."""
        if not self._has_provider(source):
            return
        if self._refresh_locks[source].locked():
            return

        async def _runner() -> None:
            try:
                await self.refresh_with_status(source, force=False)
            except Exception:
                log.exception("Eroare neașteptată la revalidarea în fundal pentru %s", source)

        task = asyncio.create_task(_runner())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _load_entry_swr(self, source: SourceName) -> tuple[dict | None, DataMeta]:
        """Citește din cache cu stale-while-revalidate și înregistrează telemetria."""
        t0 = time.perf_counter()
        entry = await self._read_entry(source)
        read_ms = (time.perf_counter() - t0) * 1000.0

        if entry is not None:
            meta, needs_revalidate = self._build_meta(entry)
            await self._record_telemetry(
                source,
                operation="cache_read",
                latency_ms=read_ms,
                cache_hit=True,
                status="stale" if meta.is_stale else "ok",
                error=meta.error,
            )
            if needs_revalidate:
                self._schedule_background_refresh(source)
            return entry, meta

        # Cache miss (prima pornire / cache gol)
        await self._record_telemetry(
            source,
            operation="cache_read",
            latency_ms=read_ms,
            cache_hit=False,
            status="miss",
        )

        if self._has_provider(source):
            res = await self.refresh_with_status(source, force=True)
            entry = await self._read_entry(source)
            if entry is not None:
                meta, _ = self._build_meta(entry)
                return entry, meta
            meta, _ = self._build_meta(None, fallback_error=res.error)
            return None, meta

        last_err = await self._get_source_last_error(source)
        meta, _ = self._build_meta(None, fallback_error=last_err)
        return None, meta

    # ------------------------------------------------------------------
    # Refresh surse (folosit de API `/api/refresh/{widget}` și de scheduler)
    # ------------------------------------------------------------------

    async def refresh_with_status(
        self, widget: str, *, force: bool = False
    ) -> RefreshResult:
        """Actualizează o sursă din adaptor, salvează în SQLite și nu ridică excepții."""
        if widget not in CACHE_SOURCES:
            return RefreshResult(widget=widget, success=False, latency_ms=0.0, error="Sursă necunoscută", skipped=True)

        source: SourceName = widget  # type: ignore[assignment]
        now_mono = time.monotonic()
        last_attempt = self._last_refresh_attempt.get(source)
        if (
            not force
            and last_attempt is not None
            and (now_mono - last_attempt) < self._min_manual_refresh_interval_s
        ):
            return RefreshResult(widget=source, success=True, latency_ms=0.0, skipped=True)

        async with self._refresh_locks[source]:
            self._last_refresh_attempt[source] = time.monotonic()
            t0 = time.perf_counter()
            try:
                ttl_s = await self.get_ttl(source)
                if source == "email":
                    if self._mail_provider is None:
                        raise SourceError("email", "Adaptorul de email nu este configurat")
                    emails = await self._mail_provider.fetch_inbox(limit=self._email_fetch_limit)
                    emails = await self._apply_local_read_state(emails)
                    payload = json.dumps([e.model_dump(mode="json") for e in emails])
                    origin = (
                        DataSource.MOCK
                        if getattr(self._mail_provider, "mode", "live") == "mock"
                        else DataSource.LIVE
                    )
                    await self._write_entry("email", payload, ttl_s=ttl_s, origin_source=origin)

                elif source == "weather":
                    if self._weather_provider is None:
                        raise SourceError("weather", "Adaptorul meteo nu este configurat")
                    cfg = await self._config_store.get_config()
                    weather = await self._weather_provider.fetch(
                        latitude=cfg.latitude,
                        longitude=cfg.longitude,
                        location_name=cfg.location_name,
                    )
                    payload = weather.model_dump_json()
                    await self._write_entry("weather", payload, ttl_s=ttl_s, origin_source=DataSource.LIVE)

                elif source == "news":
                    if self._news_provider is None:
                        raise SourceError("news", "Adaptorul de știri nu este configurat")
                    sources = [
                        s for s in await self._config_store.list_news_sources() if s.enabled
                    ]
                    items = await self._news_provider.fetch(sources)
                    payload = json.dumps([i.model_dump(mode="json") for i in items])
                    await self._write_entry("news", payload, ttl_s=ttl_s, origin_source=DataSource.LIVE)

                latency_ms = (time.perf_counter() - t0) * 1000.0
                await self._record_telemetry(
                    source,
                    operation="source_fetch",
                    latency_ms=latency_ms,
                    cache_hit=False,
                    status="ok",
                )
                return RefreshResult(widget=source, success=True, latency_ms=latency_ms)

            except SourceError as exc:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                err_msg = str(exc)
                log.warning("Eroare sursă %s: %s (retry_after=%s)", source, err_msg, exc.retry_after_s)
                await self._record_source_failure(source, err_msg)
                await self._record_telemetry(
                    source,
                    operation="source_fetch",
                    latency_ms=latency_ms,
                    cache_hit=False,
                    status="error",
                    error=err_msg,
                )
                return RefreshResult(
                    widget=source,
                    success=False,
                    latency_ms=latency_ms,
                    error=err_msg,
                    retry_after_s=exc.retry_after_s,
                )

            except Exception as exc:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                err_msg = f"[{source}] Eroare neașteptată: {exc}"
                log.exception("Eroare neașteptată la actualizarea sursei %s", source)
                await self._record_source_failure(source, err_msg)
                await self._record_telemetry(
                    source,
                    operation="source_fetch",
                    latency_ms=latency_ms,
                    cache_hit=False,
                    status="error",
                    error=err_msg,
                )
                return RefreshResult(
                    widget=source,
                    success=False,
                    latency_ms=latency_ms,
                    error=err_msg,
                )

    async def _apply_local_read_state(self, emails: list[EmailDetail]) -> list[EmailDetail]:
        """Păstrează starea de email citit local chiar dacă sursa nu a sincronizat încă."""
        def _op(conn: sqlite3.Connection) -> set[str]:
            rows = conn.execute("SELECT email_id FROM email_read_state").fetchall()
            return {r["email_id"] for r in rows}

        read_ids = await self._db.run(_op)
        if not read_ids:
            return emails
        return [
            e.model_copy(update={"is_read": True}) if (e.id in read_ids and not e.is_read) else e
            for e in emails
        ]

    # ------------------------------------------------------------------
    # Implementarea protocolului CacheService
    # ------------------------------------------------------------------

    async def get_emails(self, filter: EmailFilter, limit: int) -> Envelope[EmailList]:
        entry, meta = await self._load_entry_swr("email")
        if entry is None:
            return Envelope[EmailList](data=EmailList(items=[], unread_count=0), meta=meta)

        raw_items = json.loads(entry["payload_json"])
        all_emails = [EmailDetail.model_validate(item) for item in raw_items]
        unread_count = sum(1 for e in all_emails if not e.is_read)

        filtered = sorted(all_emails, key=lambda e: e.received_at, reverse=True)
        if filter is EmailFilter.UNREAD:
            filtered = [e for e in filtered if not e.is_read]
        elif filter is EmailFilter.PRIORITY:
            filtered = [e for e in filtered if e.is_priority]

        # Lista NU are voie să conțină câmpul `preview` (Privacy Lock)
        summaries = [
            EmailSummary(**e.model_dump(exclude={"preview"}))
            for e in filtered[:limit]
        ]
        return Envelope[EmailList](
            data=EmailList(items=summaries, unread_count=unread_count),
            meta=meta,
        )

    async def get_email(self, email_id: str) -> Envelope[EmailDetail] | None:
        entry, meta = await self._load_entry_swr("email")
        if entry is None:
            return None

        raw_items = json.loads(entry["payload_json"])
        for item in raw_items:
            if item.get("id") == email_id:
                detail = EmailDetail.model_validate(item)
                return Envelope[EmailDetail](data=detail, meta=meta)
        return None

    async def mark_read(self, email_id: str) -> None:
        now_iso = _to_iso(_now())

        def _op(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT OR REPLACE INTO email_read_state (email_id, marked_at) VALUES (?, ?)",
                (email_id, now_iso),
            )
            row = conn.execute(
                "SELECT payload_json FROM cache_entries WHERE source = 'email' AND cache_key = 'default'"
            ).fetchone()
            if row is not None:
                items = json.loads(row["payload_json"])
                changed = False
                for item in items:
                    if item.get("id") == email_id and not item.get("is_read"):
                        item["is_read"] = True
                        changed = True
                if changed:
                    conn.execute(
                        """
                        UPDATE cache_entries
                        SET payload_json = ?
                        WHERE source = 'email' AND cache_key = 'default'
                        """,
                        (json.dumps(items),),
                    )
            conn.commit()

        await self._db.run(_op)

    async def get_weather(self) -> Envelope[WeatherData]:
        entry, meta = await self._load_entry_swr("weather")
        if entry is not None:
            weather = WeatherData.model_validate_json(entry["payload_json"])
            return Envelope[WeatherData](data=weather, meta=meta)

        # Fallback valid pentru prima pornire offline (WeatherData.current este obligatoriu)
        cfg = await self._config_store.get_config()
        placeholder = WeatherData(
            location_name=cfg.location_name,
            latitude=cfg.latitude,
            longitude=cfg.longitude,
            current=WeatherCurrent(
                temperature_c=0.0,
                feels_like_c=0.0,
                humidity_pct=0,
                wind_kmh=0.0,
                condition=WeatherCondition.UNKNOWN,
                description="Date indisponibile",
            ),
            hourly=[],
            daily=[],
        )
        return Envelope[WeatherData](data=placeholder, meta=meta)

    async def get_news(self, source_id: str | None, limit: int) -> Envelope[NewsList]:
        entry, meta = await self._load_entry_swr("news")
        if entry is None:
            return Envelope[NewsList](data=NewsList(items=[]), meta=meta)

        raw_items = json.loads(entry["payload_json"])
        items = [NewsItem.model_validate(item) for item in raw_items]

        configured_sources = await self._config_store.list_news_sources()
        enabled_ids = {s.id for s in configured_sources if s.enabled}
        if enabled_ids:
            items = [n for n in items if n.source_id in enabled_ids]
        else:
            items = []

        if source_id is not None:
            items = [n for n in items if n.source_id == source_id]

        items.sort(key=lambda n: n.published_at, reverse=True)
        return Envelope[NewsList](data=NewsList(items=items[:limit]), meta=meta)

    async def refresh(self, widget: str) -> None:
        """Forțează reîmprospătarea unei surse (cu respectarea rate limiting)."""
        await self.refresh_with_status(widget, force=False)

    async def get_telemetry(self) -> list[SourceTelemetry]:
        def _op(conn: sqlite3.Connection) -> list[SourceTelemetry]:
            results: list[SourceTelemetry] = []
            for source in CACHE_SOURCES:
                state = conn.execute(
                    """
                    SELECT last_success_at, consecutive_failures
                    FROM source_state
                    WHERE source = ?
                    """,
                    (source,),
                ).fetchone()

                hit_miss = conn.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END), 0) AS hits,
                        COALESCE(SUM(CASE WHEN cache_hit = 0 THEN 1 ELSE 0 END), 0) AS misses
                    FROM telemetry
                    WHERE source = ? AND operation = 'cache_read'
                    """,
                    (source,),
                ).fetchone()

                # Preferă latențele măsurate pe sursă; dacă nu există încă fetch-uri, folosește citirile
                lat_stats = conn.execute(
                    """
                    SELECT AVG(latency_ms) AS avg_ms
                    FROM telemetry
                    WHERE source = ? AND operation = 'source_fetch'
                    """,
                    (source,),
                ).fetchone()
                last_lat_row = conn.execute(
                    """
                    SELECT latency_ms
                    FROM telemetry
                    WHERE source = ? AND operation = 'source_fetch'
                    ORDER BY id DESC LIMIT 1
                    """,
                    (source,),
                ).fetchone()

                if last_lat_row is None:
                    lat_stats = conn.execute(
                        "SELECT AVG(latency_ms) AS avg_ms FROM telemetry WHERE source = ?",
                        (source,),
                    ).fetchone()
                    last_lat_row = conn.execute(
                        "SELECT latency_ms FROM telemetry WHERE source = ? ORDER BY id DESC LIMIT 1",
                        (source,),
                    ).fetchone()

                avg_ms = round(lat_stats["avg_ms"], 2) if lat_stats and lat_stats["avg_ms"] is not None else None
                last_ms = round(last_lat_row["latency_ms"], 2) if last_lat_row else None

                results.append(
                    SourceTelemetry(
                        source=source,
                        last_latency_ms=last_ms,
                        avg_latency_ms=avg_ms,
                        cache_hits=int(hit_miss["hits"]),
                        cache_misses=int(hit_miss["misses"]),
                        last_success_at=_from_iso(state["last_success_at"]) if state else None,
                        consecutive_failures=int(state["consecutive_failures"]) if state else 0,
                    )
                )
            return results

        return await self._db.run(_op)

    async def aclose(self) -> None:
        """Oprește task-urile de revalidare în fundal și închide conexiunea SQLite."""
        for task in list(self._bg_tasks):
            task.cancel()
        for task in list(self._bg_tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._bg_tasks.clear()
        if self._owns_db:
            self._db.close()

    def close(self) -> None:
        if self._owns_db:
            self._db.close()