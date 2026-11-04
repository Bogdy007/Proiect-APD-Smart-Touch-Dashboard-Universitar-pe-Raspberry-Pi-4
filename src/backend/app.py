"""Backend Orchestrator: REST API + WebSocket pentru Smart Touch Dashboard.

Rulare locală:
    uvicorn src.backend.app:app --host 127.0.0.1 --port 8000 --reload
Documentație interactivă: http://127.0.0.1:8000/docs

app.py nu conține logică de achiziție sau cache: doar rutează cererile către
serviciile din interfaces.py. Implementările reale se injectează în create_app().
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .interfaces import AuthError, AuthService, CacheService, ConfigStore, MetricsProvider
from .mock_services import MockAuthService, MockCacheService, MockConfigStore, MockMetricsProvider
from .schemas import (
    AuthStatus,
    DashboardConfig,
    EmailDetail,
    EmailFilter,
    EmailList,
    Envelope,
    ErrorResponse,
    HealthStatus,
    NewsList,
    NewsSource,
    NewsSourceCreate,
    NewsSourceUpdate,
    SessionInfo,
    SystemMetrics,
    TelemetrySnapshot,
    UnlockRequest,
    WeatherData,
    WidgetType,
    WsEvent,
    WsEventType,
)

log = logging.getLogger("dashboard")

METRICS_PUSH_INTERVAL_S = 5


# ---------------------------------------------------------------------------
# Containerul de servicii (dependency injection)
# ---------------------------------------------------------------------------

@dataclass
class Services:
    cache: CacheService
    config: ConfigStore
    auth: AuthService
    metrics: MetricsProvider
    mail_mode: str = "mock"


def default_services() -> Services:
    """Serviciile mock. Se înlocuiesc pe măsură ce modulele reale sunt livrate."""
    config = MockConfigStore()
    return Services(
        cache=MockCacheService(config),
        config=config,
        auth=MockAuthService(session_minutes=int(os.environ.get("SESSION_TIMEOUT_MIN", "5"))),
        metrics=MockMetricsProvider(),
        mail_mode=os.environ.get("MAIL_MODE", "mock"),
    )


# ---------------------------------------------------------------------------
# WebSocket: difuzare evenimente către toate ecranele conectate
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, type: WsEventType, payload: dict | None = None) -> None:
        event = WsEvent(type=type, timestamp=datetime.now(timezone.utc), payload=payload or {})
        message = event.model_dump(mode="json")
        for ws in list(self._clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)


# ---------------------------------------------------------------------------
# Dependențe comune
# ---------------------------------------------------------------------------

def get_services(request: Request) -> Services:
    return request.app.state.services


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def get_token(authorization: Annotated[str | None, Header()] = None) -> str | None:
    return _bearer(authorization)


def require_unlocked(
    services: Annotated[Services, Depends(get_services)],
    token: Annotated[str | None, Depends(get_token)],
) -> str:
    """Protejează conținutul emailurilor și setările (Privacy Lock)."""
    if not services.auth.validate(token):
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED", "message": "Sesiune blocată."})
    return token  # type: ignore[return-value]


ServicesDep = Annotated[Services, Depends(get_services)]
UnlockedDep = Annotated[str, Depends(require_unlocked)]

ERR_401 = {401: {"model": ErrorResponse}}
ERR_404 = {404: {"model": ErrorResponse}}


# ---------------------------------------------------------------------------
# Fabrica aplicației
# ---------------------------------------------------------------------------

def create_app(services: Services | None = None) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(_metrics_loop(app))
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="Smart Touch Dashboard API", version="1.0.0", lifespan=lifespan)
    app.state.services = services or default_services()
    app.state.ws = ConnectionManager()

    # UI-ul rulează pe același RPi; în dezvoltare FE poate rula pe alt port (ex. Vite 5173).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=detail)

    _register_routes(app)
    return app


async def _metrics_loop(app: FastAPI) -> None:
    services: Services = app.state.services
    last_online: bool | None = None
    while True:
        try:
            metrics = services.metrics.read()
            await app.state.ws.broadcast(WsEventType.METRICS, metrics.model_dump(mode="json"))
            if last_online is not None and metrics.online != last_online:
                await app.state.ws.broadcast(WsEventType.CONNECTIVITY, {"online": metrics.online})
            last_online = metrics.online
        except Exception:
            log.exception("Eroare la citirea metricilor")
        await asyncio.sleep(METRICS_PUSH_INTERVAL_S)


# ---------------------------------------------------------------------------
# Rute
# ---------------------------------------------------------------------------

def _register_routes(app: FastAPI) -> None:

    # --- Health -----------------------------------------------------------
    @app.get("/api/health", response_model=HealthStatus, tags=["system"])
    async def health(s: ServicesDep):
        online = s.metrics.read().online
        return HealthStatus(status="ok" if online else "degraded", online=online, mail_mode=s.mail_mode)

    # --- Email ------------------------------------------------------------
    @app.get("/api/email", response_model=Envelope[EmailList], tags=["email"])
    async def list_emails(
        s: ServicesDep,
        filter: EmailFilter = EmailFilter.ALL,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        return await s.cache.get_emails(filter, limit)

    @app.get("/api/email/{email_id}", response_model=Envelope[EmailDetail], responses={**ERR_401, **ERR_404},
             tags=["email"])
    async def get_email(email_id: str, s: ServicesDep, _: UnlockedDep):
        result = await s.cache.get_email(email_id)
        if result is None:
            raise HTTPException(404, {"code": "NOT_FOUND", "message": "Email inexistent."})
        await s.cache.mark_read(email_id)
        return result

    # --- Vreme ------------------------------------------------------------
    @app.get("/api/weather", response_model=Envelope[WeatherData], tags=["weather"])
    async def get_weather(s: ServicesDep):
        return await s.cache.get_weather()

    # --- Știri ------------------------------------------------------------
    @app.get("/api/news", response_model=Envelope[NewsList], tags=["news"])
    async def get_news(
        s: ServicesDep,
        source_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
    ):
        return await s.cache.get_news(source_id, limit)

    @app.get("/api/news/sources", response_model=list[NewsSource], tags=["news"])
    async def list_sources(s: ServicesDep):
        return await s.config.list_news_sources()

    @app.post("/api/news/sources", response_model=NewsSource, status_code=201, responses=ERR_401, tags=["news"])
    async def add_source(body: NewsSourceCreate, s: ServicesDep, _: UnlockedDep):
        src = await s.config.add_news_source(body)
        await s.cache.refresh("news")
        await app.state.ws.broadcast(WsEventType.CONFIG_UPDATED)
        return src

    @app.patch("/api/news/sources/{source_id}", response_model=NewsSource, responses={**ERR_401, **ERR_404},
               tags=["news"])
    async def update_source(source_id: str, body: NewsSourceUpdate, s: ServicesDep, _: UnlockedDep):
        src = await s.config.update_news_source(source_id, body)
        if src is None:
            raise HTTPException(404, {"code": "NOT_FOUND", "message": "Sursă inexistentă."})
        await app.state.ws.broadcast(WsEventType.CONFIG_UPDATED)
        return src

    @app.delete("/api/news/sources/{source_id}", status_code=204, responses={**ERR_401, **ERR_404}, tags=["news"])
    async def delete_source(source_id: str, s: ServicesDep, _: UnlockedDep):
        if not await s.config.delete_news_source(source_id):
            raise HTTPException(404, {"code": "NOT_FOUND", "message": "Sursă inexistentă."})
        await app.state.ws.broadcast(WsEventType.CONFIG_UPDATED)

    # --- Refresh manual ---------------------------------------------------
    @app.post("/api/refresh/{widget}", status_code=202, tags=["system"])
    async def refresh(widget: WidgetType, s: ServicesDep):
        if widget != "system":
            await s.cache.refresh(widget)
            await app.state.ws.broadcast(WsEventType.DATA_UPDATED, {"widget": widget})
        return {"accepted": True}

    # --- Configurare widget-uri ------------------------------------------
    @app.get("/api/config", response_model=DashboardConfig, tags=["config"])
    async def get_config(s: ServicesDep):
        return await s.config.get_config()

    @app.put("/api/config", response_model=DashboardConfig, responses=ERR_401, tags=["config"])
    async def put_config(body: DashboardConfig, s: ServicesDep, _: UnlockedDep):
        types = [w.type for w in body.widgets]
        if len(types) != len(set(types)):
            raise HTTPException(422, {"code": "INVALID_CONFIG", "message": "Widget duplicat în configurare."})
        saved = await s.config.save_config(body)
        await app.state.ws.broadcast(WsEventType.CONFIG_UPDATED)
        return saved

    # --- Monitorizare -----------------------------------------------------
    @app.get("/api/system/metrics", response_model=SystemMetrics, tags=["system"])
    async def system_metrics(s: ServicesDep):
        return s.metrics.read()

    @app.get("/api/system/telemetry", response_model=TelemetrySnapshot, tags=["system"])
    async def telemetry(s: ServicesDep):
        return TelemetrySnapshot(system=s.metrics.read(), sources=await s.cache.get_telemetry())

    # --- Autentificare ----------------------------------------------------
    @app.post("/api/auth/unlock", response_model=SessionInfo, responses={401: {"model": ErrorResponse},
                                                                          429: {"model": ErrorResponse}},
              tags=["auth"])
    async def unlock(body: UnlockRequest, s: ServicesDep):
        try:
            return s.auth.unlock(body.pin)
        except AuthError as e:
            raise HTTPException(429 if e.code == "LOCKED_OUT" else 401, {"code": e.code, "message": str(e)})

    @app.post("/api/auth/lock", status_code=204, tags=["auth"])
    async def lock(s: ServicesDep, token: Annotated[str | None, Depends(get_token)]):
        s.auth.lock(token)
        await app.state.ws.broadcast(WsEventType.AUTH_LOCKED)

    @app.get("/api/auth/status", response_model=AuthStatus, tags=["auth"])
    async def auth_status(s: ServicesDep, token: Annotated[str | None, Depends(get_token)]):
        return s.auth.status(token)

    # --- WebSocket --------------------------------------------------------
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        manager: ConnectionManager = app.state.ws
        await manager.connect(ws)
        try:
            while True:
                await ws.receive_text()  # mesajele clientului sunt ignorate (keep-alive)
        except WebSocketDisconnect:
            manager.disconnect(ws)


app = create_app()
