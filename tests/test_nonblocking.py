"""Teste de ne-blocare: un serviciu lent nu are voie să oprească restul API-ului.

Cerința: UI-ul răspunde în < 150 ms, iar rețeaua rulează asincron.
Când livrezi un modul real, adaugă clasa ta în ASYNC_IMPLEMENTATIONS.
"""

import asyncio
import inspect
import time

import httpx
import pytest

from src.backend import interfaces
from src.backend.app import Services, create_app
from src.backend.mock_services import (
    MockAuthService,
    MockCacheService,
    MockConfigStore,
    MockMetricsProvider,
)
from src.backend.schemas import SessionInfo

SLOW_S = 0.5      # cât durează serviciul lent simulat
FAST_LIMIT_S = 0.25  # o rută rapidă trebuie să răspundă sub acest prag

ASYNC_PROTOCOLS = [
    interfaces.MailProvider,
    interfaces.WeatherProvider,
    interfaces.NewsProvider,
    interfaces.CacheService,
    interfaces.ConfigStore,
]

# (clasa implementării, protocolul pe care îl implementează)
ASYNC_IMPLEMENTATIONS = [
    (MockCacheService, interfaces.CacheService),
    (MockConfigStore, interfaces.ConfigStore),
]


def _protocol_methods(protocol) -> list[str]:
    return [n for n, v in vars(protocol).items() if inspect.isfunction(v) and not n.startswith("_")]


@pytest.mark.parametrize("protocol", ASYNC_PROTOCOLS, ids=lambda p: p.__name__)
def test_async_protocols_stay_async(protocol):
    sync = [n for n in _protocol_methods(protocol) if not inspect.iscoroutinefunction(getattr(protocol, n))]
    assert not sync, f"{protocol.__name__}: metode care trebuie să fie async: {sync}"


@pytest.mark.parametrize("impl,protocol", ASYNC_IMPLEMENTATIONS, ids=lambda x: x.__name__)
def test_implementations_are_async(impl, protocol):
    sync = [n for n in _protocol_methods(protocol) if not inspect.iscoroutinefunction(getattr(impl, n))]
    assert not sync, f"{impl.__name__}: metode care trebuie să fie async: {sync}"


# ---------------------------------------------------------------------------
# Servicii sincrone lente (simulează psutil și hash-ul scrypt al PIN-ului)
# ---------------------------------------------------------------------------

class SlowMetrics(MockMetricsProvider):
    def read(self):
        time.sleep(SLOW_S)
        return super().read()


class SlowAuth(MockAuthService):
    def unlock(self, pin: str) -> SessionInfo:
        time.sleep(SLOW_S)
        return super().unlock(pin)


def _app(metrics=None, auth=None):
    config = MockConfigStore()
    return create_app(Services(
        cache=MockCacheService(config),
        config=config,
        auth=auth or MockAuthService(),
        metrics=metrics or MockMetricsProvider(),
    ))


async def _fast_route_time_while_slow(app, slow_request) -> float:
    """Pornește cererea lentă, apoi măsoară când termină o rută rapidă trimisă în paralel.

    Cronometrul pornește odată cu cererea lentă: dacă serviciul lent blochează
    bucla de evenimente, ruta rapidă termină abia după SLOW_S.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = time.perf_counter()
        slow = asyncio.create_task(slow_request(client))
        await asyncio.sleep(0.05)  # lasă cererea lentă să intre în serviciu
        r = await client.get("/api/weather")
        elapsed = time.perf_counter() - start
        assert r.status_code == 200
        await slow
        return elapsed


@pytest.mark.parametrize("path", ["/api/system/metrics", "/api/system/telemetry", "/api/health"])
def test_slow_metrics_do_not_block_api(path):
    app = _app(metrics=SlowMetrics())
    elapsed = asyncio.run(_fast_route_time_while_slow(app, lambda c: c.get(path)))
    assert elapsed < FAST_LIMIT_S, f"{path} a blocat serverul {elapsed:.2f}s"


def test_slow_pin_check_does_not_block_api(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PIN", "4321")
    app = _app(auth=SlowAuth())
    elapsed = asyncio.run(
        _fast_route_time_while_slow(app, lambda c: c.post("/api/auth/unlock", json={"pin": "4321"}))
    )
    assert elapsed < FAST_LIMIT_S, f"verificarea PIN-ului a blocat serverul {elapsed:.2f}s"
