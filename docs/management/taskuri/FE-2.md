# FE-2 — Frontend — Email, Setări, Performanță

**Student:** Cimpoeșu C. Ioan · **GitHub:** Pelungloane

Widget-ul de email, panoul de personalizare și panoul de performanță al RPi.

**Fișierele tale:** `src/frontend/components/EmailWidget.*`, `SettingsModal.*`, `PerformanceWidget.*`

## Sprint 1

- [ ] `EmailWidget.*` din `GET /api/email?filter=…`: expeditor, subiect, oră; filtre necitite/prioritare; buton refresh (`POST /api/refresh/email`)
- [ ] Deschiderea previzualizării din `GET /api/email/{id}` (cere PIN — tratează `AUTH_REQUIRED`)

## Sprint 2

- [ ] `SettingsModal.*`: activare/dezactivare, reordonare (butoane sus/jos), interval refresh → `PUT /api/config`; surse RSS → `/api/news/sources`
- [ ] Ecranul PIN (`POST /api/auth/unlock`), ascunderea datelor private la `auth_locked` pe `/ws`
- [ ] `PerformanceWidget.*`: temperatură CPU, încărcare, RAM (`/api/system/metrics` sau evenimentul `metrics` pe WS), latențe și hit rate (`/api/system/telemetry`)

## Sprint 3

- [ ] Repară problemele din auditul QA; opțional evidențierea emailurilor urgente

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/fe2-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/fe2-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
