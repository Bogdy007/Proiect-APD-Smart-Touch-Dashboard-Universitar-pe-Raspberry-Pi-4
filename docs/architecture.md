# Arhitectura Smart Touch Dashboard

> Responsabil: Technical Lead · Versiune contract: **1.0.0** (`SCHEMA_VERSION` în `src/backend/schemas.py`)
> Orice modificare a schemelor sau a API-ului se face prin PR cu review TL și se anunță echipei.

## 1. Vedere de ansamblu

Arhitectură client-server **locală**, rulând integral pe Raspberry Pi 4 #2:

```
┌──────────────────────────────────────────────────────────────────┐
│ Chromium --kiosk (touchscreen)            src/frontend/   FE-1/2 │
│ [Email] [Vreme] [Știri] [Sistem] [Setări] [PIN Lock]             │
└───────────────┬───────────────────────────────▲──────────────────┘
                │ REST (pull)                   │ WebSocket /ws (push)
┌───────────────▼───────────────────────────────┴──────────────────┐
│ Backend Orchestrator (FastAPI)     src/backend/app.py         TL │
│ rutare · validare · Privacy Lock · difuzare evenimente           │
└──────┬──────────────────────┬─────────────────────┬──────────────┘
       │ CacheService         │ AuthService         │ MetricsProvider
       │ ConfigStore          │                     │
┌──────▼───────────┐  ┌───────▼─────────┐  ┌────────▼────────────┐
│ Cache + Scheduler│  │ Auth & Vault    │  │ RPi Metrics         │
│ src/cache/ CACHE │  │ src/security/SEC│  │ src/monitoring/     │
│ SQLite, TTL, SWR │  │ PIN, tokeni     │  │ DEVOPS (psutil)     │
└──────▲───────────┘  └─────────────────┘  └─────────────────────┘
       │ MailProvider / WeatherProvider / NewsProvider
┌──────┴─────────────────────────────────────────────────────────────┐
│ Adaptoare (src/adapters/)                                          │
│ Mail real (MAIL-1) │ Mail mock (MAIL-2) │ Meteo + RSS (DATA-WN)    │
└────────────────────────────────────────────────────────────────────┘
```

**Principiu de bază:** UI-ul nu vorbește niciodată cu internetul. Citește doar din backend, iar backend-ul citește doar din cache. Achiziția rulează în fundal, decuplată de cererile UI, deci o sursă externă căzută nu blochează niciodată ecranul.

## 2. Fluxul datelor

```
Scheduler (CACHE) ──interval / refresh manual──▶ Adaptor.fetch()
      │                                              │
      │◀── date normalizate (modele schemas.py) ─────┤ succes
      │◀── SourceError ──────────────────────────────┘ eșec → backoff exponențial
      ▼
SQLite cache (date + fetched_at + telemetrie)
      │
      ▼
app.py ── Envelope{data, meta} ──▶ UI  (meta.is_stale → „Mod Offline – date din urmă cu X min”)
      │
      └── WS data_updated ──▶ UI re-cere widget-ul
```

1. **Achiziție:** scheduler-ul apelează adaptoarele la `refresh_interval_s` al fiecărui widget.
2. **Normalizare:** adaptorul convertește răspunsul extern (JSON, XML/RSS, IMAP) în modelele din `schemas.py`. Curățarea HTML, sanitizarea, conversia unităților și deduplicarea se fac **în adaptor**.
3. **Persistare:** cache-ul salvează datele împreună cu `fetched_at` și actualizează telemetria (latență, hit/miss, eșecuri consecutive).
4. **Servire:** `app.py` cere datele de la `CacheService` și le returnează în `Envelope`.
5. **Notificare:** după un refresh reușit, backend-ul trimite `data_updated` pe WebSocket.

## 3. Responsabilități pe module

| Modul | Fișiere | Implementează | Owner |
|---|---|---|---|
| Orchestrator | `src/backend/app.py`, `schemas.py`, `interfaces.py` | rute, contracte | TL |
| Mail real | `src/adapters/mail_client.py`, `mail_parser.py` | `MailProvider` (`mode="real"`) | MAIL-1 |
| Mail mock + filtre | `src/adapters/mock_mail_provider.py`, `mail_service.py` | `MailProvider` (`mode="mock"`), comutare | MAIL-2 |
| Meteo | `src/adapters/weather_adapter.py` | `WeatherProvider` | DATA-WN |
| RSS | `src/adapters/news_rss_adapter.py` | `NewsProvider` | DATA-WN |
| Cache | `src/cache/cache_manager.py`, `scheduler.py` | `CacheService`, `ConfigStore` | CACHE |
| Securitate | `src/security/auth_manager.py`, `credential_store.py` | `AuthService` | SEC |
| Monitorizare | `src/monitoring/rpi_metrics.py` | `MetricsProvider` | DEVOPS |
| UI | `src/frontend/` | consumă API-ul de mai jos | FE-1, FE-2 |

Până la livrarea modulelor reale, `app.py` folosește implementările din `src/backend/mock_services.py`. Fiecare owner își înlocuiește mock-ul în `default_services()` printr-un PR.

## 4. Contracte între module

### 4.1 Adaptoare → Cache

- Metodele sunt `async`; HTTP-ul se face cu `httpx.AsyncClient` și timeout explicit (recomandat 10 s).
- Returnează **doar** modele din `schemas.py`, deja normalizate.
- La orice eșec ridică `SourceError(source, message, retry_after_s)`. Nu returnează `None` și nici liste goale pentru a semnala o eroare.
- Nu cunosc cache-ul și nu fac retry: retry-ul și backoff-ul aparțin scheduler-ului.

### 4.2 Cache → Backend

- **Nu ridică excepții** pentru surse căzute: returnează ultimele date valide, cu `meta.source="cache"`, `meta.is_stale=True` și `meta.error` completat.
- Dacă nu există încă date (prima pornire fără internet), returnează date goale (`items=[]`) cu `is_stale=True`.
- Backoff exponențial: `min(base * 2^n, 15 min)` cu jitter, plus respectarea `retry_after_s` la HTTP 429.

### 4.3 Securitate

- Lista de emailuri (expeditor, subiect) e vizibilă fără PIN. **Previzualizarea** (`GET /api/email/{id}`) și **orice modificare** de setări cer o sesiune deblocată.
- Token de sesiune trimis ca `Authorization: Bearer <token>`. Fiecare cerere validă prelungește sesiunea; după `auto_lock_minutes` de inactivitate, sesiunea expiră.
- După 5 PIN-uri greșite urmează blocare temporară (HTTP 429, `LOCKED_OUT`).
- Secretele (PIN, credențiale IMAP/OAuth, chei API) se citesc **doar** din `.env` sau din stocare criptată. `.env` este în `.gitignore`.

## 5. Specificația API (v1)

Bază: `http://127.0.0.1:8000`. Documentație interactivă generată automat: `/docs` (Swagger) și `/openapi.json`.
🔒 = cere `Authorization: Bearer <token>`.

### Date

| Metodă | Rută | Răspuns | Note |
|---|---|---|---|
| GET | `/api/email?filter=all\|unread\|priority&limit=20` | `Envelope[EmailList]` | fără previzualizare |
| GET 🔒 | `/api/email/{id}` | `Envelope[EmailDetail]` | marchează ca citit |
| GET | `/api/weather` | `Envelope[WeatherData]` | curent + orar + zilnic |
| GET | `/api/news?source_id=&limit=30` | `Envelope[NewsList]` | descrescător după dată |
| POST | `/api/refresh/{email\|weather\|news}` | `202` | refresh manual (pull-to-refresh) |

### Configurare

| Metodă | Rută | Corp / Răspuns |
|---|---|---|
| GET | `/api/config` | `DashboardConfig` |
| PUT 🔒 | `/api/config` | `DashboardConfig` → `DashboardConfig` |
| GET | `/api/news/sources` | `list[NewsSource]` |
| POST 🔒 | `/api/news/sources` | `NewsSourceCreate` → `NewsSource` (201) |
| PATCH 🔒 | `/api/news/sources/{id}` | `NewsSourceUpdate` → `NewsSource` |
| DELETE 🔒 | `/api/news/sources/{id}` | `204` |

### Sistem și autentificare

| Metodă | Rută | Răspuns |
|---|---|---|
| GET | `/api/health` | `HealthStatus` |
| GET | `/api/system/metrics` | `SystemMetrics` |
| GET | `/api/system/telemetry` | `TelemetrySnapshot` (latențe, hit rate) |
| POST | `/api/auth/unlock` | `UnlockRequest` → `SessionInfo`; 401 `INVALID_PIN`, 429 `LOCKED_OUT` |
| POST | `/api/auth/lock` | `204` |
| GET | `/api/auth/status` | `AuthStatus` |

### Format `Envelope`

```json
{
  "data": { "...": "modelul specific" },
  "meta": {
    "source": "live | cache | mock",
    "fetched_at": "2026-11-04T10:15:00Z",
    "age_seconds": 420,
    "is_stale": true,
    "error": "timeout"
  }
}
```

### Erori

Toate erorile au forma `{"code": "...", "message": "..."}`. Coduri stabile: `AUTH_REQUIRED`, `INVALID_PIN`, `LOCKED_OUT`, `NOT_FOUND`, `INVALID_CONFIG`. FE decide comportamentul după `code`, nu după `message`.

### WebSocket `/ws`

Server → client, mesaje `WsEvent`: `{"type": "...", "timestamp": "...", "payload": {...}}`

| `type` | `payload` | Reacția UI |
|---|---|---|
| `data_updated` | `{"widget": "email"}` | re-cere widget-ul |
| `connectivity_changed` | `{"online": false}` | actualizează bara de stare |
| `auth_locked` | `{}` | ascunde datele private |
| `metrics` | `SystemMetrics` (la 5 s) | actualizează widget-ul Sistem |
| `config_updated` | `{}` | re-cere `/api/config` |

Clientul se reconectează automat cu backoff (1 s, 2 s, 4 s, maxim 30 s).

## 6. Cerințe nefuncționale: cum le acoperă arhitectura

| Cerință | Soluție |
|---|---|
| Răspuns UI < 150 ms | UI-ul citește doar din cache-ul local, iar rețeaua rulează asincron în scheduler |
| Funcționare offline | stale-while-revalidate, `meta.is_stale` și indicator vizual |
| Rate limiting | interval minim de 30 s per widget, backoff exponențial, `Retry-After` |
| Fără memory leaks | clienți `httpx` reutilizați, limită pe numărul de rânduri din cache, rulare de 60 min monitorizată |
| Fără secrete în Git | `.env` + `credential_store.py`, `.env.example` fără valori |

## 7. Decizii tehnice

| Decizie | Motiv |
|---|---|
| Python 3.11+ cu FastAPI | async nativ, validare Pydantic, OpenAPI generat automat pentru FE |
| React + Vite (frontend) | componente reutilizabile pentru widget-uri, build rapid, bundle mic servit static de Chromium în kiosk |
| SQLite | persistent, fără server, potrivit pentru RPi |
| REST + WebSocket | REST pentru citiri și comenzi, WS pentru push (metrici, stare) fără polling |
| Interfețe `Protocol` + DI în `create_app()` | module dezvoltate în paralel, testabile cu mock-uri |
| Backend legat de `127.0.0.1` | API-ul nu e expus în rețea; kiosk-ul rulează local |

## 8. Rulare locală

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn src.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

## 9. Reguli de lucru (Git)

- `main` protejat: doar prin PR, cel puțin 1 aprobare (TL pentru `src/backend/` și pentru modificări de scheme) și CI verde.
- Branch-uri: `feat/<rol>-<descriere>`, `fix/<rol>-<descriere>` (ex. `feat/mail2-mock-engine`).
- Modificarea schemelor: PR separat, incrementarea `SCHEMA_VERSION` și anunț pe canalul echipei.
