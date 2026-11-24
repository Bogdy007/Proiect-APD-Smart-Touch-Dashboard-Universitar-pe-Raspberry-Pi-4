"""Scheduler asincron în fundal pentru actualizarea periodică a surselor de date.

Responsabilități (CACHE):
  - Rulează câte o buclă independentă per sursă (`email`, `weather`, `news`),
    respectând `refresh_interval_s` și starea `enabled` din `ConfigStore`.
  - La erori ale surselor aplică backoff exponențial `min(base * 2^n, 15 min)`
    cu jitter și respectă `retry_after_s` (ex. header-ul HTTP 429 Retry-After).
  - La revenirea rețelei (`on_connectivity_restored`) reia sincronizarea imediat.
  - Notifică backend-ul prin callback-ul opțional `on_data_updated(widget)` pentru
    difuzarea evenimentului WebSocket `data_updated`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.backend.interfaces import ConfigStore
from src.cache.cache_manager import CACHE_SOURCES, DEFAULT_TTLS, SourceName, SQLiteCacheManager

log = logging.getLogger("dashboard.scheduler")

MAX_BACKOFF_S = 15 * 60.0  # 15 minute conform specificației CACHE


def compute_backoff_delay(
    consecutive_failures: int,
    *,
    base_s: float = 15.0,
    max_s: float = MAX_BACKOFF_S,
    retry_after_s: float | None = None,
    jitter_ratio: float = 0.2,
    rng: random.Random | None = None,
) -> float:
    """Calculează întârzierea backoff `min(base * 2^n, max_s)` cu jitter și `retry_after_s`."""
    n = max(1, consecutive_failures)
    raw_delay = min(base_s * (2 ** n), max_s)

    if jitter_ratio > 0:
        gen = rng or random
        factor = 1.0 + gen.uniform(-jitter_ratio, jitter_ratio)
        delay = max(0.0, min(raw_delay * factor, max_s))
    else:
        delay = raw_delay

    if retry_after_s is not None and retry_after_s > 0:
        return max(delay, float(retry_after_s))
    return delay


@dataclass(slots=True)
class SourceScheduleState:
    consecutive_failures: int = 0
    last_error: str | None = None
    next_run_at: datetime | None = None
    running: bool = False


class CacheScheduler:
    """Orchestrează refresh-ul periodic al surselor în fundal fără a bloca API-ul."""

    def __init__(
        self,
        cache: SQLiteCacheManager,
        config_store: ConfigStore,
        *,
        on_data_updated: Callable[[str], Awaitable[None]] | None = None,
        backoff_base_s: float = 15.0,
        backoff_max_s: float = MAX_BACKOFF_S,
        jitter_ratio: float = 0.2,
        run_immediately: bool = True,
        rng: random.Random | None = None,
    ) -> None:
        self._cache = cache
        self._config_store = config_store
        self._on_data_updated = on_data_updated
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        self._jitter_ratio = jitter_ratio
        self._run_immediately = run_immediately
        self._rng = rng

        self._stop_event = asyncio.Event()
        self._wake_events: dict[SourceName, asyncio.Event] = {
            s: asyncio.Event() for s in CACHE_SOURCES
        }
        self._tasks: dict[SourceName, asyncio.Task] = {}
        self._states: dict[SourceName, SourceScheduleState] = {
            s: SourceScheduleState() for s in CACHE_SOURCES
        }

    @property
    def is_running(self) -> bool:
        return any(not t.done() for t in self._tasks.values())

    def get_state(self, source: SourceName) -> SourceScheduleState:
        return self._states[source]

    async def start(self) -> None:
        """Pornește task-urile de fundal pentru toate sursele (idempotent)."""
        if self.is_running:
            return
        self._stop_event.clear()
        for source in CACHE_SOURCES:
            self._wake_events[source].clear()
            self._states[source].running = True
            self._tasks[source] = asyncio.create_task(
                self._source_loop(source),
                name=f"cache-scheduler-{source}",
            )
        log.info("CacheScheduler pornit pentru sursele: %s", ", ".join(CACHE_SOURCES))

    async def stop(self) -> None:
        """Oprește curat toate task-urile de fundal."""
        self._stop_event.set()
        for event in self._wake_events.values():
            event.set()
        for source, task in list(self._tasks.items()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            self._states[source].running = False
        self._tasks.clear()
        log.info("CacheScheduler oprit.")

    def trigger_refresh(self, widget: str | None = None) -> None:
        """Trezește imediat bucla unei surse (sau a tuturor) pentru sincronizare."""
        if widget is None:
            for event in self._wake_events.values():
                event.set()
        elif widget in self._wake_events:
            self._wake_events[widget].set()  # type: ignore[index]

    async def on_connectivity_restored(self) -> None:
        """Resetează starea de backoff și declanșează resincronizarea imediată a tuturor surselor."""
        for source in CACHE_SOURCES:
            self._states[source].consecutive_failures = 0
            self._wake_events[source].set()
        log.info("Conexiune restabilită: resincronizare declanșată pentru toate sursele.")

    async def _widget_settings(self, source: SourceName) -> tuple[bool, float]:
        """Returnează `(enabled, refresh_interval_s)` pentru sursa dată."""
        try:
            cfg = await self._config_store.get_config()
            for w in cfg.widgets:
                if w.type == source:
                    return w.enabled, float(w.refresh_interval_s)
        except Exception:
            log.exception("Nu s-a putut citi configurarea widget-ului %s", source)
        return True, float(DEFAULT_TTLS.get(source, 300))

    async def _wait_interruptible(self, source: SourceName, delay_s: float) -> bool:
        """Așteaptă `delay_s` secunde; întoarce False dacă scheduler-ul a primit stop."""
        if self._stop_event.is_set():
            return False

        wake = self._wake_events[source]
        self._states[source].next_run_at = datetime.now(timezone.utc) + timedelta(seconds=delay_s)

        stop_task = asyncio.create_task(self._stop_event.wait())
        wake_task = asyncio.create_task(wake.wait())
        try:
            done, pending = await asyncio.wait(
                {stop_task, wake_task},
                timeout=max(0.0, delay_s),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for p in pending:
                p.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await p
            if wake_task in done:
                wake.clear()
            return not self._stop_event.is_set()
        finally:
            for t in (stop_task, wake_task):
                if not t.done():
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await t

    async def _source_loop(self, source: SourceName) -> None:
        state = self._states[source]
        first_iteration = True

        while not self._stop_event.is_set():
            enabled, interval_s = await self._widget_settings(source)

            if first_iteration and not self._run_immediately:
                first_iteration = False
                if not await self._wait_interruptible(source, interval_s):
                    break
                continue
            first_iteration = False

            if not enabled:
                if not await self._wait_interruptible(source, interval_s):
                    break
                continue

            result = await self._cache.refresh_with_status(source, force=True)

            if result.success:
                state.consecutive_failures = 0
                state.last_error = None
                if self._on_data_updated is not None and not result.skipped:
                    try:
                        await self._on_data_updated(source)
                    except Exception:
                        log.exception("Eroare în callback-ul on_data_updated pentru %s", source)
                delay_s = interval_s
            else:
                state.consecutive_failures += 1
                state.last_error = result.error
                delay_s = compute_backoff_delay(
                    state.consecutive_failures,
                    base_s=self._backoff_base_s,
                    max_s=self._backoff_max_s,
                    retry_after_s=result.retry_after_s,
                    jitter_ratio=self._jitter_ratio,
                    rng=self._rng,
                )
                log.warning(
                    "Sursa %s a eșuat (#%d); următoarea încercare peste %.1fs",
                    source,
                    state.consecutive_failures,
                    delay_s,
                )

            if not await self._wait_interruptible(source, delay_s):
                break